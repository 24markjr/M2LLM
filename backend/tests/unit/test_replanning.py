"""Phase 16 — the adaptive replanning loop.

Two things must hold above all: the loop always terminates, and every stop records a
distinct, honest reason. A loop that can run forever is not adaptive, and one that stops
silently is indistinguishable from one that gave up.
"""

from __future__ import annotations

import json

from app.core.events import EventBus, MemoryEventSink, RunEventEmitter
from app.integrations.verification import BaselineVerifier
from app.intelligence.graph.task_graph import TaskGraph
from app.intelligence.reasoning.engine import ReasoningEngine
from app.intelligence.replanning.controller import (
    ReplanningController,
    evidence_from_observations,
    evidence_text_map,
)
from app.intelligence.router.engine import ToolRouter
from app.llm.echo import EchoProvider
from app.schemas.common import new_run_id
from app.schemas.event import EventType
from app.schemas.execution import Observation, TerminationReason
from app.schemas.objective import Objective
from app.schemas.task import Task, TaskType
from app.tools.base import ToolContext, ToolRegistry
from app.tools.builtin import DocumentExtractTool, DocumentSearchTool

DOCS = {
    "report.txt": "Target completion is 2026-04-30.\nApproved budget 380,000.\n",
    "finance.txt": "Delivery completed 2026-05-14.\nTotal spend 450,000.\n",
}

OBSERVATIONS = [
    Observation(
        task_id="task_001",
        task_type="extract_timeline",
        content="target completion 2026-04-30",
        sources=["report.txt:r1"],
    ),
    Observation(
        task_id="task_002",
        task_type="extract_timeline",
        content="delivery completed 2026-05-14",
        sources=["finance.txt:r1"],
    ),
]


def _ctx() -> ToolContext:
    return ToolContext(run_id=new_run_id(), document_ids=list(DOCS), documents=DOCS)


def _graph() -> TaskGraph:
    return TaskGraph(
        [
            Task(task_id="task_001", task_type=TaskType.EXTRACT_TIMELINE, description="extract"),
        ]
    )


def _registry() -> ToolRegistry:
    registry = ToolRegistry()
    registry.register(DocumentSearchTool())
    registry.register(DocumentExtractTool())
    return registry


def _findings(*claims: tuple[str, list[str]]) -> str:
    return json.dumps({"findings": [{"claim": c, "citations": refs} for c, refs in claims]})


def _verdict(status: str, issue: str = "nothing supports this") -> str:
    return json.dumps(
        {"status": status, "issues": [{"issue_type": "NO_EVIDENCE", "description": issue}]}
    )


def _controller(
    *,
    reasoning: list[str],
    verification: list[str],
    graph: TaskGraph | None = None,
    emit: object | None = None,
) -> tuple[ReplanningController, TaskGraph]:
    provider = EchoProvider(
        responses={"reasoning": reasoning, "verification": verification, "router": ["{}"]}
    )
    registry = _registry()
    task_graph = graph or _graph()
    controller = ReplanningController(
        graph=task_graph,
        registry=registry,
        router=ToolRouter(registry),
        reasoner=ReasoningEngine(provider),
        verifier=BaselineVerifier(provider),
        emit=emit,
    )
    return controller, task_graph


# --- the evidence pool ---------------------------------------------------------


def test_evidence_is_built_from_observation_sources() -> None:
    """Without the text behind a locator, gap detection can only see that a citation
    exists - not whether it says what the claim says it says."""
    evidence = evidence_from_observations(OBSERVATIONS)

    assert len(evidence) == 2
    assert {e.locator.as_ref() for e in evidence} == {"report.txt:r1", "finance.txt:r1"}
    assert all(e.content for e in evidence)


def test_the_text_map_is_keyed_by_locator() -> None:
    text = evidence_text_map(evidence_from_observations(OBSERVATIONS))
    assert "report.txt:r1" in text
    assert "2026-04-30" in text["report.txt:r1"]


# --- termination: the loop always stops, and says why --------------------------


async def test_all_findings_verified_terminates_as_resolved() -> None:
    controller, _ = _controller(
        reasoning=[_findings(("Completion dates differ.", ["report.txt:r1", "finance.txt:r1"]))],
        verification=[_verdict("SUPPORTED")],
    )

    result = await controller.run(Objective(text="Find contradictions."), OBSERVATIONS, _ctx())

    assert result.termination_reason is TerminationReason.ALL_RESOLVED
    assert result.iterations == 0, "nothing needed fixing"
    assert result.verified


async def test_no_findings_terminates_without_looping() -> None:
    controller, _ = _controller(reasoning=[_findings()], verification=[_verdict("SUPPORTED")])

    result = await controller.run(Objective(text="Check."), OBSERVATIONS, _ctx())

    assert result.termination_reason is TerminationReason.NO_ACTIONABLE_GAP
    assert result.findings == []


async def test_a_contradicted_finding_is_not_retried() -> None:
    """More evidence cannot rescue a claim the sources refute.

    Spending iterations on one would be the loop working hard and achieving nothing.
    """
    controller, graph = _controller(
        reasoning=[_findings(("Spend was under budget.", ["report.txt:r1"]))],
        verification=[_verdict("CONTRADICTED", "the figure shows an overrun")],
    )
    before = len(graph.tasks)

    result = await controller.run(Objective(text="Check."), OBSERVATIONS, _ctx())

    assert result.termination_reason is TerminationReason.ALL_RESOLVED
    assert len(graph.tasks) == before, "no task was inserted for a contradicted claim"


async def test_an_unsupported_finding_triggers_a_replan() -> None:
    """The headline behaviour: the plan changes mid-run."""
    controller, graph = _controller(
        reasoning=[
            _findings(("The project slipped against the approved baseline.", ["report.txt:r1"]))
        ],
        verification=[_verdict("UNSUPPORTED")],
    )
    before = len(graph.tasks)

    result = await controller.run(Objective(text="Check."), OBSERVATIONS, _ctx())

    assert len(graph.tasks) > before, "the running graph was edited"
    assert result.gaps, "gaps were detected and named"
    assert result.revisions, "the revision was recorded"


async def test_the_loop_is_bounded_by_the_iteration_ceiling() -> None:
    """A loop that can run forever is not adaptive, it is broken."""
    from app.core.agent_config import get_agent_bounds

    # A model that never produces supportable findings: without a ceiling this never ends.
    controller, _ = _controller(
        reasoning=[
            _findings(("Unsupportable claim about the approved baseline.", ["ghost.txt:r1"]))
        ],
        verification=[_verdict("UNSUPPORTED")],
    )

    result = await controller.run(Objective(text="Check."), OBSERVATIONS, _ctx())

    assert result.iterations <= get_agent_bounds().max_replan_iterations
    assert result.termination_reason in {
        TerminationReason.MAX_ITERATIONS,
        TerminationReason.DIMINISHING_RETURNS,
        TerminationReason.NO_ACTIONABLE_GAP,
    }


async def test_every_termination_records_a_reason() -> None:
    controller, _ = _controller(
        reasoning=[_findings(("A claim.", ["report.txt:r1"]))],
        verification=[_verdict("SUPPORTED")],
    )
    result = await controller.run(Objective(text="Check."), OBSERVATIONS, _ctx())
    assert result.termination_reason is not None


# --- graph mutation ------------------------------------------------------------


async def test_inserted_tasks_carry_the_gap_that_caused_them() -> None:
    """An inserted task must always be explainable."""
    controller, graph = _controller(
        reasoning=[
            _findings(("The project slipped against the approved baseline.", ["report.txt:r1"]))
        ],
        verification=[_verdict("UNSUPPORTED")],
    )

    await controller.run(Objective(text="Check."), OBSERVATIONS, _ctx())

    inserted = [t for t in graph.tasks if t.created_for_gap_id]
    assert inserted
    assert all(t.task_type is TaskType.RETRIEVE_EVIDENCE for t in inserted)


async def test_the_graph_stays_acyclic_after_replanning() -> None:
    controller, graph = _controller(
        reasoning=[
            _findings(("The project slipped against the approved baseline.", ["report.txt:r1"]))
        ],
        verification=[_verdict("UNSUPPORTED")],
    )

    await controller.run(Objective(text="Check."), OBSERVATIONS, _ctx())

    assert graph.find_cycle() == [], "every mutation re-validates acyclicity"


async def test_higher_severity_gaps_are_addressed_first() -> None:
    """If the budget runs out, it should run out on the gaps that mattered least."""
    controller, _ = _controller(
        reasoning=[
            _findings(("Slipped against the approved baseline by 2026-09-09.", ["report.txt:r1"]))
        ],
        verification=[_verdict("UNSUPPORTED")],
    )

    result = await controller.run(Objective(text="Check."), OBSERVATIONS, _ctx())

    # Under the cost-aware policy (Phase 17) ordering is by score, of which severity is one
    # input. What must hold is that the best-scoring candidate was acted on and that every
    # candidate's score was recorded with its working.
    assert result.scores, "the policy recorded a score breakdown for each candidate"

    addressed = {g.gap_id for g in result.gaps if g.resolved_by_task_id}
    best = max(result.scores, key=lambda s: s.score)
    assert best.gap_id in addressed, "the highest-scoring action must be acted on"

    for score in result.scores:
        assert score.explain(), "a score must be inspectable, not a bare number"


# --- tracing: the loop is visible ----------------------------------------------


async def test_the_loop_is_fully_traced() -> None:
    memory = MemoryEventSink()
    emitter = RunEventEmitter(EventBus([memory]), new_run_id())
    controller, _ = _controller(
        reasoning=[
            _findings(("The project slipped against the approved baseline.", ["report.txt:r1"]))
        ],
        verification=[_verdict("UNSUPPORTED")],
        emit=emitter,
    )

    await controller.run(Objective(text="Check."), OBSERVATIONS, _ctx())

    types = [e.event_type for e in memory.events]
    assert EventType.VERIFICATION_STARTED in types
    assert EventType.EVIDENCE_GAP_DETECTED in types
    assert EventType.REPLAN_STARTED in types
    assert EventType.TASK_CREATED in types
    assert EventType.PLAN_REVISED in types


async def test_the_trace_shows_the_gap_before_the_replan_it_caused() -> None:
    """Order is the proof. Replanning cannot precede the gap that triggered it."""
    memory = MemoryEventSink()
    emitter = RunEventEmitter(EventBus([memory]), new_run_id())
    controller, _ = _controller(
        reasoning=[
            _findings(("The project slipped against the approved baseline.", ["report.txt:r1"]))
        ],
        verification=[_verdict("UNSUPPORTED")],
        emit=emitter,
    )

    await controller.run(Objective(text="Check."), OBSERVATIONS, _ctx())

    types = [e.event_type for e in memory.events]
    assert types.index(EventType.EVIDENCE_GAP_DETECTED) < types.index(EventType.REPLAN_STARTED)
    assert types.index(EventType.REPLAN_STARTED) < types.index(EventType.TASK_CREATED)


async def test_the_detected_gap_names_what_is_missing_in_the_trace() -> None:
    memory = MemoryEventSink()
    emitter = RunEventEmitter(EventBus([memory]), new_run_id())
    controller, _ = _controller(
        reasoning=[
            _findings(("The project slipped against the approved baseline.", ["report.txt:r1"]))
        ],
        verification=[_verdict("UNSUPPORTED")],
        emit=emitter,
    )

    await controller.run(Objective(text="Check."), OBSERVATIONS, _ctx())

    gap_events = memory.of_type(EventType.EVIDENCE_GAP_DETECTED)
    assert gap_events
    assert any("baseline" in str(e.payload.get("missing", "")) for e in gap_events)
