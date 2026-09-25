"""The API-to-database path: does a mission survive a restart?

`DatabaseEventSink` and the repositories were built and tested in Phase 3, and nothing wired them to
the API - so every run lived in memory and a restart lost all of it. These tests cover the wiring,
which is the part that was missing rather than the part that was broken.

Runs against a real Postgres. The point is the round trip, and an in-memory substitute would verify
that the substitute works.
"""

from __future__ import annotations

import asyncio
from contextlib import suppress

import pytest
from sqlalchemy import func, select

from app.api import persistence
from app.api.persistence import record_finished, record_started
from app.api.registry import MissionRecord, get_registry, reset_registry
from app.database.repositories import RunRepository
from app.database.session import database_available, dispose_engine, session_scope
from app.models.tables import ExecutionEvent, Finding
from app.orchestration.mission import MissionResult, MissionStatus
from app.schemas.common import new_run_id
from app.schemas.objective import Objective


def _available() -> bool:
    """Whether a database is reachable, decided at collection time.

    The probe runs in its own event loop and disposes the engine afterwards: a pooled connection
    created here cannot be closed under the loop a test later runs in, which surfaces as
    `RuntimeError: Event loop is closed` from inside asyncpg and points nowhere useful.
    """
    try:
        return asyncio.run(database_available())
    except OSError:
        return False
    finally:
        with suppress(Exception):
            asyncio.run(dispose_engine())


requires_db = pytest.mark.skipif(
    not _available(), reason="no database reachable (docker compose up -d postgres)"
)


@pytest.fixture(autouse=True)
def _clean() -> None:
    reset_registry()
    persistence.reset_persistence_probe()


def _record(status: MissionStatus = MissionStatus.COMPLETED) -> MissionRecord:
    record = MissionRecord(new_run_id(), Objective(text="Check the Aurora reports."), ["a.txt"])
    record.status = status
    record.result = MissionResult(run_id=record.run_id, objective=record.objective, status=status)
    return record


async def _delete(run_id: str) -> None:
    async with session_scope() as session:
        await RunRepository(session).delete(run_id)


# --- the wiring that was missing -------------------------------------------------


@requires_db
async def test_a_started_run_gets_a_row_before_it_produces_anything() -> None:
    """Written at the start, not the end: every other table references this row, and a run that
    crashed mid-flight is exactly the one worth having a record of."""
    record = _record(MissionStatus.RUNNING)
    try:
        await record_started(record)

        async with session_scope() as session:
            row = await RunRepository(session).get(record.run_id)

        assert row is not None
        assert row.objective == "Check the Aurora reports."
        assert row.model, "the model that ran it is recorded"
    finally:
        await _delete(record.run_id)


@requires_db
async def test_a_finished_run_survives_a_new_session() -> None:
    """The whole point. A fresh session is what a restart looks like from the database's side."""
    record = _record()
    try:
        await record_started(record)
        await record_finished(record)

        # A separate session and repository instance - nothing carried over in memory.
        async with session_scope() as session:
            row = await RunRepository(session).get(record.run_id)
            assert row is not None
            assert row.status == "COMPLETED"
            assert row.final_result is not None
            assert row.final_result["status"] == "COMPLETED"
    finally:
        await _delete(record.run_id)


@requires_db
async def test_a_finished_run_is_stored_even_if_the_start_write_was_lost() -> None:
    """Persistence may become reachable mid-run, or the first write may simply have failed.

    Dropping the finished run because its opening row is missing would lose the more valuable half.
    """
    record = _record()
    try:
        await record_finished(record)  # no record_started

        async with session_scope() as session:
            assert await RunRepository(session).get(record.run_id) is not None
    finally:
        await _delete(record.run_id)


@requires_db
async def test_a_failed_run_is_persisted_too() -> None:
    """Storing only successful runs would make the stored history look better than the system is."""
    record = _record(MissionStatus.FAILED)
    assert record.result is not None
    record.result.error_code = "PLAN_INVALID"
    record.result.error_message = "no terminal task"
    try:
        await record_started(record)
        await record_finished(record)

        async with session_scope() as session:
            row = await RunRepository(session).get(record.run_id)

        assert row is not None
        assert row.status == "FAILED"
        assert row.final_result is not None
        assert row.final_result["error_code"] == "PLAN_INVALID"
    finally:
        await _delete(record.run_id)


@requires_db
async def test_a_clarification_request_is_a_completed_run_not_a_failed_one() -> None:
    """Refusing to plan on a guessed objective is the correct outcome, and the stored status should
    not describe it as a failure."""
    record = _record(MissionStatus.CLARIFICATION_NEEDED)
    try:
        await record_started(record)
        await record_finished(record)

        async with session_scope() as session:
            row = await RunRepository(session).get(record.run_id)

        assert row is not None
        assert row.status == "COMPLETED"
    finally:
        await _delete(record.run_id)


# --- the registry end to end ----------------------------------------------------


@requires_db
async def test_a_mission_run_through_the_registry_persists_its_timeline() -> None:
    """The path a real request takes: the registry starts a mission, and its events land in the
    database as well as in memory."""
    from app.llm.echo import EchoProvider

    registry = get_registry()
    record = await registry.create(
        objective=Objective(text="Investigate the reports for contradictions."),
        documents=["a.txt"],
        loaded={"a.txt": "Target completion 2026-04-30.\nApproved budget 380,000.\n"},
        page_starts={},
        provider=EchoProvider(),
    )

    assert record.task is not None
    await record.task

    try:
        async with session_scope() as session:
            run = await RunRepository(session).get(record.run_id)
            events = await session.scalar(
                select(func.count())
                .select_from(ExecutionEvent)
                .where(ExecutionEvent.run_id == record.run_id)
            )

        assert run is not None, "the registry did not persist the run"
        assert events and events > 0, "the run's timeline was not persisted"
        assert len(record.events) > 0, "and it is still in memory for SSE replay"
    finally:
        await _delete(record.run_id)


@requires_db
async def test_findings_are_stored_whole_including_the_rejected_ones() -> None:
    """Keeping only what passed verification would make every stored run look better supported than
    it was - the same reason an unresolvable citation is kept rather than dropped."""
    from app.schemas.finding import Confidence, FindingClassification
    from app.schemas.finding import Finding as FindingSchema

    record = _record()
    assert record.result is not None
    record.result.findings = [
        FindingSchema(
            finding_id="F-001",
            claim="The dates conflict.",
            classification=FindingClassification.UNKNOWN,
            confidence=Confidence.compute(refs=[], classification=FindingClassification.UNKNOWN),
        )
    ]

    try:
        await record_started(record)
        await record_finished(record)

        async with session_scope() as session:
            stored = await session.scalar(
                select(func.count()).select_from(Finding).where(Finding.run_id == record.run_id)
            )

        assert stored == 1, "an unsupported finding must be stored, not filtered out"
    finally:
        await _delete(record.run_id)


# --- and it must not require a database ------------------------------------------


async def test_persistence_is_optional_and_silent_when_unavailable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The demo runs with no database at all. Requiring Postgres to watch the agent work would make
    it harder to try for no benefit, so an unreachable database must be a no-op rather than an
    error - and must not raise into a run that already produced its findings.

    Runs whether or not a database is present, because this is the path most people will take.
    """
    monkeypatch.setattr("app.api.persistence.database_available", _never)
    persistence.reset_persistence_probe()

    record = _record()

    # Neither call may raise, and neither may write anything.
    await record_started(record)
    await record_finished(record)

    assert await persistence.persistence_enabled() is False


async def _never() -> bool:
    return False


@requires_db
async def test_a_write_failure_never_reaches_the_run(monkeypatch: pytest.MonkeyPatch) -> None:
    """An investigation that reached its findings must report them whether or not a row was
    written. Losing the record of a good run is bad; losing the run to save the record is worse.
    """

    def _explode(*_args: object, **_kwargs: object) -> None:
        raise RuntimeError("the database went away mid-write")

    monkeypatch.setattr("app.api.persistence.session_scope", _explode)
    record = _record()

    await record_started(record)
    await record_finished(record)  # must not raise
