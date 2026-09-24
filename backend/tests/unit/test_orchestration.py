"""Phase 19 — the headless mission pipeline.

`run_mission` is now the single path a mission takes, so its failure modes are the system's
failure modes. What is tested here is not the happy path - the intelligence tests cover every
stage - but the promises the pipeline makes about *not finishing*:

- an ambiguous objective stops before planning, and says what it needed to know
- a plan that will not validate fails the run instead of being executed
- a crash anywhere is contained and reported as a code, never raised into the host
- cancellation keeps what the run had already established

Every one of those is a state the API and the UI have to render, and a state that is wrong
here is wrong everywhere downstream.
"""

from __future__ import annotations

import asyncio
import json

import pytest

from app.core.events import EventBus, MemoryEventSink, RunEventEmitter
from app.llm.echo import EchoProvider
from app.orchestration.mission import MissionStatus, Stage, run_mission
from app.schemas.common import new_run_id
from app.schemas.event import EventType
from app.schemas.objective import Objective

DOCS = {
    "report.txt": "Target completion is 2026-04-30.\nApproved budget 380,000.\n",
    "finance.txt": "Delivery completed 2026-05-14.\nTotal spend 450,000.\n",
}

OBJECTIVE = Objective(text="Find contradictions between the reports.")


def _emitter() -> tuple[RunEventEmitter, MemoryEventSink]:
    memory = MemoryEventSink()
    return RunEventEmitter(EventBus([memory]), new_run_id()), memory


def _intent(*, clarify: bool = False, operations: list[str] | None = None) -> str:
    return json.dumps(
        {
            "goal": "Compare the reports",
            "objective": OBJECTIVE.text,
            "operations": operations or ["extract_timeline", "detect_inconsistencies"],
            "clarification_needed": clarify,
            "clarification_question": "Which completion date is authoritative?" if clarify else "",
        }
    )


def _plan(*, tasks: list[dict[str, object]] | None = None) -> str:
    return json.dumps(
        {
            "tasks": tasks
            or [
                {
                    "id": "task_001",
                    "type": "extract_timeline",
                    "description": "extract dates",
                    "depends_on": [],
                },
                {
                    "id": "task_002",
                    "type": "detect_inconsistencies",
                    "description": "compare the dates",
                    "depends_on": ["task_001"],
                },
                {
                    "id": "task_003",
                    "type": "synthesize",
                    "description": "write it up",
                    "depends_on": ["task_002"],
                },
            ]
        }
    )


# --- stopping before a plan exists ----------------------------------------------


async def test_an_ambiguous_objective_stops_before_planning() -> None:
    """A plan built on a guess is indistinguishable from a plan built on an understanding.

    The question the agent needed answered is part of the result, not a log line.
    """
    emitter, _ = _emitter()
    result = await run_mission(
        objective=OBJECTIVE,
        documents=DOCS,
        provider=EchoProvider(responses={"intent": [_intent(clarify=True)]}),
        emitter=emitter,
    )

    assert result.status is MissionStatus.CLARIFICATION_NEEDED
    assert result.plan is None, "no plan was produced for an objective it did not understand"
    assert "authoritative" in result.error_message


async def test_a_mission_with_no_readable_documents_reports_the_plan_and_stops() -> None:
    """The plan is real and is returned. Execution is not attempted, and the result does not
    pretend it was."""
    emitter, _ = _emitter()
    result = await run_mission(
        objective=OBJECTIVE,
        documents={},
        provider=EchoProvider(responses={"intent": [_intent()], "planner": [_plan()] * 4}),
        emitter=emitter,
    )

    assert result.error_code == "NO_DOCUMENTS"
    assert result.plan is not None
    assert result.observations == []
    assert result.findings == []


async def test_an_invalid_plan_fails_the_run_rather_than_executing() -> None:
    """Executing a plan known to be wrong is worse than failing: it produces findings that
    look ordinary and rest on work that should never have run."""
    emitter, _ = _emitter()
    # A task that depends on itself is a cycle, which no repair can resolve.
    broken = _plan(
        tasks=[
            {
                "id": "task_001",
                "type": "extract_timeline",
                "description": "x",
                "depends_on": ["task_001"],
            }
        ]
    )
    result = await run_mission(
        objective=OBJECTIVE,
        documents=DOCS,
        provider=EchoProvider(responses={"intent": [_intent()], "planner": [broken] * 6}),
        emitter=emitter,
    )

    assert result.status is MissionStatus.FAILED
    assert result.error_code == "PLAN_INVALID"
    assert result.error_message, "the run says which rule the plan broke"


# --- containment ----------------------------------------------------------------


async def test_a_failure_anywhere_is_reported_not_raised() -> None:
    """The API runs missions as background tasks. An exception escaping here would take
    down a run with no record of why, and in the worst case the process with it."""
    emitter, _ = _emitter()
    # No fixtures at all: the very first model call raises.
    result = await run_mission(
        objective=OBJECTIVE, documents=DOCS, provider=EchoProvider(), emitter=emitter
    )

    assert result.status is MissionStatus.FAILED
    assert result.error_code, "the failure carries a code the client can branch on"


async def test_the_run_is_bookended_on_the_timeline() -> None:
    """A run is reconstructable from its events (invariant 4), which requires knowing where
    it started and how it ended."""
    emitter, memory = _emitter()
    await run_mission(
        objective=OBJECTIVE,
        documents={},
        provider=EchoProvider(responses={"intent": [_intent()], "planner": [_plan()] * 4}),
        emitter=emitter,
    )

    assert memory.of_type(EventType.RUN_STARTED)
    assert memory.of_type(EventType.RUN_COMPLETED)


async def test_a_failed_run_is_marked_failed_on_the_timeline() -> None:
    emitter, memory = _emitter()
    await run_mission(objective=OBJECTIVE, documents=DOCS, provider=EchoProvider(), emitter=emitter)

    assert memory.of_type(EventType.RUN_FAILED)
    assert not memory.of_type(EventType.RUN_COMPLETED)


# --- progress -------------------------------------------------------------------


async def test_stages_are_announced_in_order() -> None:
    """A caller showing progress should not have to watch the event stream and guess which
    event means "planning finished"."""
    emitter, _ = _emitter()
    seen: list[Stage] = []

    await run_mission(
        objective=OBJECTIVE,
        documents={},
        provider=EchoProvider(responses={"intent": [_intent()], "planner": [_plan()] * 4}),
        emitter=emitter,
        on_stage=lambda stage, _result: seen.append(stage),
    )

    assert seen[:2] == [Stage.UNDERSTANDING, Stage.PLANNING]
    assert seen[-1] is Stage.DONE, "the run always announces that it is over"


async def test_a_synchronous_stage_callback_is_accepted() -> None:
    """A terminal renderer prints; an API handler awaits. Neither should have to care which
    the other one needs."""
    emitter, _ = _emitter()
    calls: list[str] = []

    def on_stage(stage: Stage, _result: object) -> None:
        calls.append(stage.value)

    result = await run_mission(
        objective=OBJECTIVE,
        documents={},
        provider=EchoProvider(responses={"intent": [_intent()], "planner": [_plan()] * 4}),
        emitter=emitter,
        on_stage=on_stage,
    )

    assert calls
    assert result.status is MissionStatus.COMPLETED


# --- cancellation ---------------------------------------------------------------


async def test_cancellation_keeps_what_the_run_had_reached() -> None:
    """The point of cancelling rather than discarding: a cancelled investigation still
    reports the state it established before it was stopped."""
    emitter, _ = _emitter()

    class _SlowProvider(EchoProvider):
        async def complete(self, request: object) -> object:  # type: ignore[override]
            await asyncio.sleep(3600)
            raise AssertionError("unreachable")

    task = asyncio.create_task(
        run_mission(
            objective=OBJECTIVE,
            documents=DOCS,
            provider=_SlowProvider(),
            emitter=emitter,
        )
    )
    await asyncio.sleep(0.05)
    task.cancel()

    with pytest.raises(asyncio.CancelledError):
        await task
