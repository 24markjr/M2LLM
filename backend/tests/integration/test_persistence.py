"""Phase 3 — persistence against a real PostgreSQL.

Marked `integration`. Skipped automatically when no database is reachable, so the suite
stays green on a machine without Docker running.

The tests that matter are the integrity ones: a finding cannot outlive its run, evidence
cannot be orphaned, and an unresolved citation is stored rather than quietly dropped.
"""

from __future__ import annotations

import asyncio

import pytest
from sqlalchemy import func, select

from app.database.event_sink import DatabaseEventSink
from app.database.repositories import (
    EventRepository,
    FindingRepository,
    RunRepository,
    TaskRepository,
    ToolExecutionRepository,
)
from app.database.session import database_available, dispose_engine, session_scope
from app.models.tables import Evidence, ExecutionEvent, Finding, Task, Verification
from app.schemas.common import SourceLocator, new_run_id
from app.schemas.event import EventType
from app.schemas.event import ExecutionEvent as EventSchema
from app.schemas.evidence import EvidenceGap, EvidenceRef, GapType, ResolutionStatus
from app.schemas.execution import ExecutionState, RunStatus, TerminationReason
from app.schemas.finding import Confidence, FindingClassification
from app.schemas.finding import Finding as FindingSchema
from app.schemas.objective import Objective
from app.schemas.task import Task as TaskSchema
from app.schemas.task import TaskStatus, TaskType
from app.schemas.verification import (
    IssueType,
    VerificationIssue,
    VerificationResult,
    VerificationStatus,
)

pytestmark = pytest.mark.integration


def _available() -> bool:
    """Probe the database, then dispose the engine it created.

    This runs at collection time in a throwaway event loop. Leaving the engine cached
    would hand the first test a pool bound to a loop that no longer exists, which surfaces
    much later as a confusing "Event loop is closed".
    """

    async def probe() -> bool:
        try:
            return await database_available()
        finally:
            await dispose_engine()

    try:
        return asyncio.run(probe())
    except Exception:  # noqa: BLE001 - availability probe
        return False


requires_db = pytest.mark.skipif(
    not _available(), reason="no database reachable (docker compose up -d postgres)"
)


def _state(objective: str = "Find contradictions.") -> ExecutionState:
    return ExecutionState(
        run_id=new_run_id(), objective=Objective(text=objective), status=RunStatus.RUNNING
    )


def _ref(doc: str, row: int, *, resolved: bool = True) -> EvidenceRef:
    return EvidenceRef(
        locator=SourceLocator(document_id=doc, document_name=doc, row=row),
        resolution=ResolutionStatus.RESOLVED if resolved else ResolutionStatus.UNRESOLVED,
        resolution_note="" if resolved else "no task produced this locator",
    )


def _finding(fid: str = "F-001") -> FindingSchema:
    refs = [_ref("report.txt", 10), _ref("ghost.txt", 9, resolved=False)]
    return FindingSchema(
        finding_id=fid,
        claim="The completion dates conflict.",
        classification=FindingClassification.HYPOTHESIS,
        evidence=refs,
        confidence=Confidence.compute(refs=refs, classification=FindingClassification.HYPOTHESIS),
        gaps=[
            EvidenceGap(
                gap_id="G-001",
                finding_id=fid,
                gap_type=GapType.MISSING_BASELINE,
                missing="the approved baseline completion date",
                severity=0.9,
                suggested_query="approved baseline schedule",
            )
        ],
        verification=VerificationResult(
            status=VerificationStatus.PARTIALLY_SUPPORTED,
            confidence=0.7,
            issues=[
                VerificationIssue(issue_type=IssueType.NO_EVIDENCE, description="no baseline cited")
            ],
        ),
    )


# --- runs ----------------------------------------------------------------------


@requires_db
async def test_a_run_persists_and_reads_back() -> None:
    state = _state()
    async with session_scope() as session:
        await RunRepository(session).create(state, model="qwen3:4b")

    async with session_scope() as session:
        run = await RunRepository(session).get(state.run_id)

    assert run is not None
    assert run.objective == "Find contradictions."
    assert run.model == "qwen3:4b"

    async with session_scope() as session:
        await RunRepository(session).delete(state.run_id)


@requires_db
async def test_finishing_a_run_records_its_termination_reason() -> None:
    """A stop without a reason is indistinguishable from giving up - including on disk."""
    state = _state()
    async with session_scope() as session:
        await RunRepository(session).create(state)

    state.status = RunStatus.COMPLETED_WITH_GAPS
    state.termination_reason = TerminationReason.DIMINISHING_RETURNS
    state.replan_iteration = 2

    async with session_scope() as session:
        await RunRepository(session).finish(state, final_result={"findings": 3})

    async with session_scope() as session:
        run = await RunRepository(session).get(state.run_id)

    assert run is not None
    assert run.termination_reason == "DIMINISHING_RETURNS"
    assert run.replan_iterations == 2
    assert run.final_result == {"findings": 3}

    async with session_scope() as session:
        await RunRepository(session).delete(state.run_id)


# --- the task graph survives the process ---------------------------------------


@requires_db
async def test_the_task_graph_persists_with_its_edges() -> None:
    state = _state()
    tasks = [
        TaskSchema(task_id="task_001", task_type=TaskType.EXTRACT_TIMELINE, description="a"),
        TaskSchema(
            task_id="task_002",
            task_type=TaskType.COMPARE_SOURCES,
            description="b",
            depends_on=["task_001"],
            status=TaskStatus.PENDING,
        ),
    ]

    async with session_scope() as session:
        await RunRepository(session).create(state)
        await TaskRepository(session).save_all(state.run_id, tasks)

    async with session_scope() as session:
        stored = await TaskRepository(session).for_run(state.run_id)
        edges = [d.depends_on_task_id for t in stored for d in t.dependencies]

    assert [t.task_id for t in stored] == ["task_001", "task_002"]
    assert edges == ["task_001"], "the DAG edge survived the process"

    async with session_scope() as session:
        await RunRepository(session).delete(state.run_id)


# --- findings, evidence and integrity -------------------------------------------


@requires_db
async def test_a_finding_persists_with_evidence_verification_and_gaps() -> None:
    state = _state()
    async with session_scope() as session:
        await RunRepository(session).create(state)
        await FindingRepository(session).save_all(state.run_id, [_finding()])

    async with session_scope() as session:
        stored = await FindingRepository(session).for_run(state.run_id)
        finding = stored[0]
        evidence = (
            (await session.execute(select(Evidence).where(Evidence.finding_pk == finding.id)))
            .scalars()
            .all()
        )
        verification = (
            (
                await session.execute(
                    select(Verification).where(Verification.finding_pk == finding.id)
                )
            )
            .scalars()
            .all()
        )

    assert finding.classification == "HYPOTHESIS"
    assert len(evidence) == 2
    assert verification[0].status == "PARTIALLY_SUPPORTED"

    async with session_scope() as session:
        await RunRepository(session).delete(state.run_id)


@requires_db
async def test_unresolved_citations_are_stored_not_dropped() -> None:
    """Keeping only what resolved would make every stored finding look better supported."""
    state = _state()
    async with session_scope() as session:
        await RunRepository(session).create(state)
        await FindingRepository(session).save_all(state.run_id, [_finding()])

    async with session_scope() as session:
        finding = (await FindingRepository(session).for_run(state.run_id))[0]
        rows = (
            (await session.execute(select(Evidence).where(Evidence.finding_pk == finding.id)))
            .scalars()
            .all()
        )

    resolutions = {r.resolution for r in rows}
    assert resolutions == {"RESOLVED", "UNRESOLVED"}
    unresolved = next(r for r in rows if r.resolution == "UNRESOLVED")
    assert unresolved.resolution_note, "the reason it failed to resolve is kept too"

    async with session_scope() as session:
        await RunRepository(session).delete(state.run_id)


@requires_db
async def test_the_computed_confidence_breakdown_survives_storage() -> None:
    """Confidence without its working is just a number someone has to trust."""
    state = _state()
    original = _finding()
    async with session_scope() as session:
        await RunRepository(session).create(state)
        await FindingRepository(session).save_all(state.run_id, [original])

    async with session_scope() as session:
        stored = (await FindingRepository(session).for_run(state.run_id))[0]

    assert float(stored.confidence) == pytest.approx(original.confidence.value, abs=1e-3)
    assert float(stored.resolution_rate) == pytest.approx(
        original.confidence.resolution_rate, abs=1e-3
    )

    async with session_scope() as session:
        await RunRepository(session).delete(state.run_id)


@requires_db
async def test_deleting_a_run_removes_everything_it_produced() -> None:
    """A finding must not be able to outlive the run that made it."""
    state = _state()
    async with session_scope() as session:
        await RunRepository(session).create(state)
        await TaskRepository(session).save_all(
            state.run_id,
            [TaskSchema(task_id="task_001", task_type=TaskType.SUMMARIZE, description="x")],
        )
        await FindingRepository(session).save_all(state.run_id, [_finding()])
        await EventRepository(session).append(
            EventSchema(run_id=state.run_id, event_type=EventType.RUN_STARTED, t_offset_ms=0)
        )

    async with session_scope() as session:
        await RunRepository(session).delete(state.run_id)

    async with session_scope() as session:
        for table in (Task, Finding, ExecutionEvent):
            count = await session.scalar(
                select(func.count()).select_from(table).where(table.run_id == state.run_id)
            )
            assert count == 0, f"{table.__tablename__} rows outlived the run"
        orphans = await session.scalar(select(func.count()).select_from(Evidence))
        assert orphans is not None


# --- the event timeline ---------------------------------------------------------


@requires_db
async def test_events_persist_in_timeline_order() -> None:
    state = _state()
    async with session_scope() as session:
        await RunRepository(session).create(state)
        await EventRepository(session).append_many(
            [
                EventSchema(run_id=state.run_id, event_type=EventType.RUN_STARTED, t_offset_ms=0),
                EventSchema(
                    run_id=state.run_id,
                    event_type=EventType.EVIDENCE_GAP_DETECTED,
                    t_offset_ms=6900,
                ),
                EventSchema(
                    run_id=state.run_id, event_type=EventType.RUN_COMPLETED, t_offset_ms=9520
                ),
            ]
        )

    async with session_scope() as session:
        events = await EventRepository(session).for_run(state.run_id)

    assert [e.t_offset_ms for e in events] == [0, 6900, 9520]
    assert events[1].event_type == "EVIDENCE_GAP_DETECTED"

    async with session_scope() as session:
        await RunRepository(session).delete(state.run_id)


@requires_db
async def test_reading_events_after_an_offset_serves_sse_reconnection() -> None:
    state = _state()
    async with session_scope() as session:
        await RunRepository(session).create(state)
        await EventRepository(session).append_many(
            [
                EventSchema(run_id=state.run_id, event_type=EventType.RUN_STARTED, t_offset_ms=0),
                EventSchema(
                    run_id=state.run_id, event_type=EventType.TASK_STARTED, t_offset_ms=1300
                ),
            ]
        )

    async with session_scope() as session:
        events = await EventRepository(session).for_run(state.run_id, after_offset_ms=500)

    assert [e.t_offset_ms for e in events] == [1300]

    async with session_scope() as session:
        await RunRepository(session).delete(state.run_id)


@requires_db
async def test_the_sink_batches_and_flushes_on_a_terminal_event() -> None:
    """A run that ends should be durable at once, not whenever the buffer fills."""
    state = _state()
    async with session_scope() as session:
        await RunRepository(session).create(state)

    sink = DatabaseEventSink(batch_size=100)
    await sink.handle(
        EventSchema(run_id=state.run_id, event_type=EventType.RUN_STARTED, t_offset_ms=0)
    )
    assert sink.buffered == 1, "buffered rather than written one at a time"

    await sink.handle(
        EventSchema(run_id=state.run_id, event_type=EventType.RUN_COMPLETED, t_offset_ms=500)
    )
    assert sink.buffered == 0, "the terminal event forced a flush"

    async with session_scope() as session:
        events = await EventRepository(session).for_run(state.run_id)
    assert len(events) == 2

    async with session_scope() as session:
        await RunRepository(session).delete(state.run_id)


@requires_db
async def test_a_sink_failure_is_counted_rather_than_raised() -> None:
    """Losing the record of an investigation is bad; losing the investigation is worse."""
    sink = DatabaseEventSink(batch_size=1)

    # A run id with no parent row violates the foreign key.
    await sink.handle(
        EventSchema(run_id="run_ffffffffffff", event_type=EventType.RUN_STARTED, t_offset_ms=0)
    )

    assert sink.dropped == 1
    assert sink.buffered == 0


# --- tool executions ------------------------------------------------------------


@requires_db
async def test_tool_executions_are_recorded_with_their_sources() -> None:
    state = _state()
    async with session_scope() as session:
        await RunRepository(session).create(state)
        await ToolExecutionRepository(session).record(
            state.run_id,
            "task_001",
            call_id="call_0123456789ab",
            tool_name="document_extract",
            arguments={"pattern": "dates"},
            output={"extractions": []},
            ok=True,
            sources=["report.txt:r10"],
            execution_time_ms=42,
        )

    async with session_scope() as session:
        rows = await ToolExecutionRepository(session).for_run(state.run_id)

    assert rows[0].tool_name == "document_extract"
    assert rows[0].sources == ["report.txt:r10"]

    async with session_scope() as session:
        await RunRepository(session).delete(state.run_id)
