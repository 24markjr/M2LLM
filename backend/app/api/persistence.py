"""Persisting a mission, without letting persistence break one.

`DatabaseEventSink` and the repositories have existed since Phase 3 and were tested against a real
Postgres, but nothing wired them to the API - so a restart lost every run. This closes that.

Two rules shape the whole module.

**Persistence is optional.** The demo runs with no database at all: `python -m app.cli investigate`
needs only Ollama, and requiring Postgres to see the agent work would make the thing harder to try
for no benefit. Availability is checked once per process; when there is no database, runs proceed
exactly as before and say so once in the log rather than once per event.

**Persistence never fails a run.** Every write here is contained. An investigation that reached its
findings must report them whether or not a row was written - losing the record of a good run is bad,
and losing the run itself to save the record would be worse. Failures are logged and counted, which
is what makes a silent gap in the history impossible.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from app.core.config import get_settings
from app.core.logging import get_logger
from app.database.repositories import FindingRepository, RunRepository, TaskRepository
from app.database.session import database_available, session_scope
from app.orchestration.mission import MissionStatus
from app.schemas.execution import ExecutionState, RunPhase, RunStatus

if TYPE_CHECKING:
    from app.api.registry import MissionRecord

log = get_logger(__name__)

# Checked once, not per run. `database_available()` opens a connection, and doing that on every
# mission would add a round trip to a path that is meant to start returning immediately.
_available: bool | None = None

# Mission status -> the run status stored on the row. Explicit rather than a string cast: these are
# two separate vocabularies and a rename on either side should be a type error, not a silent
# mismatch in a column nobody reads until they need it.
_RUN_STATUS = {
    MissionStatus.PENDING: RunStatus.PENDING,
    MissionStatus.RUNNING: RunStatus.RUNNING,
    MissionStatus.COMPLETED: RunStatus.COMPLETED,
    MissionStatus.FAILED: RunStatus.FAILED,
    MissionStatus.CANCELLED: RunStatus.CANCELLED,
    # Refusing to plan on a guess is a completed run with a question as its result, not a failure.
    MissionStatus.CLARIFICATION_NEEDED: RunStatus.COMPLETED,
}


async def persistence_enabled() -> bool:
    """Whether runs will be stored. Determined once per process."""
    global _available
    if _available is None:
        _available = await database_available()
        if _available:
            log.info("run_persistence_enabled")
        else:
            log.info(
                "run_persistence_disabled",
                reason="no database reachable; runs will not survive a restart",
            )
    return _available


def reset_persistence_probe() -> None:
    """Forget the availability result. For tests, and after a config change."""
    global _available
    _available = None


async def record_started(record: MissionRecord) -> None:
    """Insert the run row, so events and findings have something to belong to.

    Written before the mission starts rather than after it finishes: every other table references
    this row, and a run that crashed mid-flight is exactly the one worth having a record of.
    """
    if not await persistence_enabled():
        return

    try:
        async with session_scope() as session:
            await RunRepository(session).create(_state(record), model=get_settings().ollama_model)
        log.debug("run_row_created", run_id=record.run_id)
    except Exception:
        log.exception("run_persist_failed", run_id=record.run_id, stage="started")


async def record_finished(record: MissionRecord) -> None:
    """Update the run row and store the tasks and findings it produced.

    Findings are stored whole - unresolved evidence alongside resolved, rejected findings alongside
    verified. Keeping only what passed would make every stored run look better than it was, which is
    the one thing a persisted record must not do.
    """
    if not await persistence_enabled():
        return

    result = record.result
    state = _state(record)

    try:
        async with session_scope() as session:
            runs = RunRepository(session)
            if await runs.get(record.run_id) is None:
                # The start write failed, or persistence became available mid-run. Insert now
                # rather than dropping the finished run on the floor.
                await runs.create(state, model=get_settings().ollama_model)

            await runs.finish(state, final_result=_final_result(record))

            if result is not None:
                if result.plan is not None and result.plan.tasks:
                    # `result.plan` carries the executed graph, so tasks the replanning loop
                    # inserted are stored too - see BUG-013.
                    await TaskRepository(session).save_all(record.run_id, result.plan.tasks)
                if result.findings:
                    await FindingRepository(session).save_all(record.run_id, result.findings)

        log.info(
            "run_persisted",
            run_id=record.run_id,
            status=record.status.value,
            findings=len(result.findings) if result else 0,
        )
    except Exception:
        log.exception("run_persist_failed", run_id=record.run_id, stage="finished")


def _state(record: MissionRecord) -> ExecutionState:
    """The `ExecutionState` the repositories are written against.

    `MissionResult` is what the pipeline returns and `ExecutionState` is what the database stores;
    this is the one place that translates, so neither has to know about the other.
    """
    result = record.result
    state = ExecutionState(
        run_id=record.run_id,
        objective=record.objective,
        status=_RUN_STATUS.get(record.status, RunStatus.RUNNING),
        created_at=record.created_at,
        started_at=record.started_at,
        completed_at=record.finished_at,
    )

    if result is None:
        return state

    state.intent = result.intent
    state.plan = result.plan
    state.tasks = list(result.plan.tasks) if result.plan else []
    state.observations = list(result.observations)
    state.findings = list(result.findings)
    state.gaps = list(result.gaps)
    state.revisions = list(result.revisions)
    state.replan_iteration = result.replan_iterations
    state.termination_reason = result.termination_reason
    state.current_phase = RunPhase.SYNTHESIZING if result.report else RunPhase.UNDERSTANDING
    return state


def _final_result(record: MissionRecord) -> dict[str, object]:
    """A small summary on the run row, so a listing needs no joins.

    Counts only. The report itself lives in its own tables, and duplicating it here would give two
    places to disagree about what a run found.
    """
    result = record.result
    if result is None:
        return {"status": record.status.value}

    return {
        "status": record.status.value,
        "findings": len(result.findings),
        "verified": len(result.verified_findings),
        "gaps": len(result.gaps),
        "unresolved_gaps": len(result.unresolved_gaps),
        "replan_iterations": result.replan_iterations,
        "termination_reason": (
            result.termination_reason.value if result.termination_reason else ""
        ),
        "error_code": result.error_code,
        "has_report": result.report is not None,
    }
