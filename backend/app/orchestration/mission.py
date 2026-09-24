"""The mission pipeline, headless.

    objective -> intent -> plan -> execute -> reason -> verify -> gaps -> replan -> report

This is the same sequence the CLI has always run, with the printing taken out. It exists
because the API needs to run a mission without a terminal attached, and two copies of the
sequence would drift: the moment the API grew its own pipeline, a fix to one would silently
not apply to the other.

**Stages are announced, not inferred.** A caller that wants to show progress gets an
`on_stage` callback rather than having to watch the event stream and guess which event means
"planning finished". The CLI uses it to print as the run proceeds; the API uses it to keep a
mission's current phase queryable while the run is still going.

**Cancellation is cooperative.** `run_mission` is an ordinary coroutine, so cancelling the
task that runs it raises `CancelledError` at the next await point - which is always a tool
call or a model call boundary, never mid-write. The result is marked `CANCELLED` and
whatever the run had already established is kept: a cancelled investigation still reports
the findings it reached.
"""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from enum import StrEnum

from pydantic import Field

from app.core.logging import get_logger
from app.integrations.verification import build_verification_provider
from app.intelligence.execution.engine import ExecutionEngine
from app.intelligence.graph.task_graph import TaskGraph
from app.intelligence.intent.engine import IntentEngine
from app.intelligence.planner.engine import PlanInvalidError, Planner
from app.intelligence.reasoning.engine import ReasoningEngine
from app.intelligence.replanning.controller import ReplanningController
from app.intelligence.router.engine import ToolRouter
from app.intelligence.synthesis.engine import SynthesisEngine
from app.llm.provider import LLMProvider
from app.schemas.common import JarvisModel, RunId
from app.schemas.event import EventType
from app.schemas.evidence import EvidenceGap
from app.schemas.execution import Observation, TerminationReason
from app.schemas.finding import Finding
from app.schemas.intent import Intent
from app.schemas.objective import Objective
from app.schemas.plan import Plan, PlanRevision
from app.schemas.result import ExecutionSummary, FinalReport
from app.schemas.task import TaskStatus
from app.tools.base import ToolContext, build_default_registry

log = get_logger(__name__)

# A progress callback. Sync or async: a terminal renderer prints, an API handler awaits
# a database write, and neither should have to care which the other one needs.
StageCallback = Callable[["Stage", "MissionResult"], Awaitable[None] | None]


class Stage(StrEnum):
    """The phases a caller can show a progress indicator for.

    Deliberately coarser than `EventType`: a user watching a run wants seven phases, not
    thirty-nine event kinds. The event log remains the complete record.
    """

    UNDERSTANDING = "UNDERSTANDING"
    PLANNING = "PLANNING"
    EXECUTING = "EXECUTING"
    REASONING = "REASONING"
    VERIFYING = "VERIFYING"
    REPLANNING = "REPLANNING"
    SYNTHESIZING = "SYNTHESIZING"
    DONE = "DONE"


class MissionStatus(StrEnum):
    PENDING = "PENDING"
    RUNNING = "RUNNING"
    COMPLETED = "COMPLETED"
    # The objective was too ambiguous to plan against. Not a failure: refusing to plan on a
    # guess is the correct outcome, and the question asked is part of the result.
    CLARIFICATION_NEEDED = "CLARIFICATION_NEEDED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"


class MissionResult(JarvisModel):
    """Everything a run established, whether or not it finished.

    Every field is optional or defaulted on purpose. A run that failed in planning has an
    intent and no plan, and a cancelled run has whatever it reached - reporting partial
    state honestly is more useful than reporting nothing.
    """

    run_id: RunId
    objective: Objective
    status: MissionStatus = MissionStatus.PENDING
    stage: Stage = Stage.UNDERSTANDING

    intent: Intent | None = None
    plan: Plan | None = None
    observations: list[Observation] = Field(default_factory=list)
    findings: list[Finding] = Field(default_factory=list)
    gaps: list[EvidenceGap] = Field(default_factory=list)
    revisions: list[PlanRevision] = Field(default_factory=list)
    report: FinalReport | None = None

    replan_iterations: int = 0
    termination_reason: TerminationReason | None = None

    # Why the run did not complete. A code the client can branch on, plus a message a
    # person can read - never a raw exception string.
    error_code: str = ""
    error_message: str = ""

    @property
    def verified_findings(self) -> list[Finding]:
        return [f for f in self.findings if f.is_verified]

    @property
    def unresolved_gaps(self) -> list[EvidenceGap]:
        return [g for g in self.gaps if not g.resolved]


async def run_mission(
    *,
    objective: Objective,
    documents: dict[str, str],
    provider: LLMProvider,
    emitter: object,
    page_starts: dict[str, list[int]] | None = None,
    on_stage: StageCallback | None = None,
    synthesize: bool = True,
) -> MissionResult:
    """Run one mission end to end and return what it established.

    Raises nothing for an ordinary failure: a plan that will not validate, or an objective
    too ambiguous to plan against, are outcomes of a run and are reported in the result.
    `CancelledError` is the one exception that propagates - after the result has been
    marked, so a caller holding the result still sees what the run reached.
    """
    result = MissionResult(
        run_id=_run_id(emitter), objective=objective, status=MissionStatus.RUNNING
    )
    await _emit(emitter, EventType.RUN_STARTED, {"objective": objective.text})

    try:
        await _advance(result, Stage.UNDERSTANDING, on_stage)
        result.intent = await IntentEngine(provider).analyze(objective, emit=emitter)

        if result.intent.clarification_needed:
            # Planning stops here. An ambiguous objective must not produce a plan: a plan
            # built on a guess looks exactly like a plan built on an understanding.
            result.status = MissionStatus.CLARIFICATION_NEEDED
            result.error_code = "CLARIFICATION_NEEDED"
            result.error_message = result.intent.clarification_question or ""
            await _finish(result, emitter, on_stage, EventType.RUN_COMPLETED)
            return result

        await _advance(result, Stage.PLANNING, on_stage)
        try:
            result.plan = await Planner(provider).create_plan(
                result.intent, objective, emit=emitter
            )
        except PlanInvalidError as exc:
            # The run fails cleanly rather than executing a plan known to be wrong.
            result.status = MissionStatus.FAILED
            result.error_code = "PLAN_INVALID"
            result.error_message = "; ".join(v.message for v in exc.result.violations)
            await _finish(result, emitter, on_stage, EventType.RUN_FAILED)
            return result

        if not documents:
            # Nothing to investigate. The plan is real and is reported; execution is not
            # attempted, and the result does not pretend it was.
            result.status = MissionStatus.COMPLETED
            result.error_code = "NO_DOCUMENTS"
            result.error_message = "no readable documents were attached to this mission"
            await _finish(result, emitter, on_stage, EventType.RUN_COMPLETED)
            return result

        registry = build_default_registry()
        graph = TaskGraph.from_plan(result.plan)
        ctx = ToolContext(
            run_id=result.run_id,
            document_ids=list(documents),
            documents=documents,
            page_starts=page_starts or {},
        )

        await _advance(result, Stage.EXECUTING, on_stage)
        router = ToolRouter(registry, provider)
        result.observations = await ExecutionEngine(graph, registry, router, emit=emitter).run(ctx)

        # Reasoning, verification, gap detection and replanning are one closed loop, not
        # four stages in sequence. The stage is announced as REASONING because that is
        # where the loop starts; the controller emits its own events throughout.
        await _advance(result, Stage.REASONING, on_stage)
        controller = ReplanningController(
            graph=graph,
            registry=registry,
            router=router,
            reasoner=ReasoningEngine(provider),
            verifier=build_verification_provider(provider),
            emit=emitter,
        )
        replan = await controller.run(objective, result.observations, ctx)

        result.findings = replan.findings
        result.gaps = replan.gaps
        result.revisions = replan.revisions
        result.observations = replan.observations
        result.replan_iterations = replan.iterations
        result.termination_reason = replan.termination_reason

        if synthesize:
            await _advance(result, Stage.SYNTHESIZING, on_stage)
            result.report = await SynthesisEngine(provider).synthesize(
                run_id=result.run_id,
                objective=objective,
                findings=result.findings,
                gaps=result.gaps,
                observations=result.observations,
                execution=_summarise(graph, documents, replan),
                termination=result.termination_reason,
                emit=emitter,
            )

        result.status = MissionStatus.COMPLETED
        await _finish(result, emitter, on_stage, EventType.RUN_COMPLETED)
        return result

    except asyncio.CancelledError:
        # Mark the result before re-raising. A caller holding it still sees the findings
        # the run had reached, which is the point of cancelling rather than discarding.
        result.status = MissionStatus.CANCELLED
        result.error_code = "CANCELLED"
        result.error_message = "the mission was cancelled"
        result.stage = Stage.DONE
        log.info("mission_cancelled", run_id=result.run_id, stage=result.stage.value)
        raise

    except Exception as exc:  # the boundary: a run must not crash the process hosting it
        result.status = MissionStatus.FAILED
        result.error_code = type(exc).__name__
        result.error_message = str(exc)
        log.exception("mission_failed", run_id=result.run_id)
        await _finish(result, emitter, on_stage, EventType.RUN_FAILED)
        return result


def _summarise(graph: TaskGraph, documents: dict[str, str], replan: object) -> ExecutionSummary:
    """Count the run. Every figure here is counted, never described by a model."""
    _, total = graph.progress()
    gaps: list[EvidenceGap] = getattr(replan, "gaps", [])
    return ExecutionSummary(
        tasks_planned=total,
        tasks_completed=len(graph.with_status(TaskStatus.COMPLETED)),
        tasks_failed=len(graph.with_status(TaskStatus.FAILED)),
        tasks_skipped=len(graph.with_status(TaskStatus.SKIPPED)),
        tool_calls=sum(1 for t in graph.tasks if t.result is not None),
        documents_processed=len(documents),
        replan_iterations=int(getattr(replan, "iterations", 0)),
        gaps_detected=len(gaps),
        gaps_resolved=sum(1 for g in gaps if g.resolved),
    )


def _run_id(emitter: object) -> RunId:
    run_id = getattr(emitter, "run_id", None)
    if not isinstance(run_id, str):  # pragma: no cover - defensive
        raise TypeError("emitter must carry a run_id")
    return run_id


async def _advance(result: MissionResult, stage: Stage, on_stage: StageCallback | None) -> None:
    result.stage = stage
    if on_stage is None:
        return
    outcome = on_stage(stage, result)
    if asyncio.iscoroutine(outcome):
        await outcome


async def _finish(
    result: MissionResult, emitter: object, on_stage: StageCallback | None, event: EventType
) -> None:
    await _emit(emitter, event, {"status": result.status.value})
    await _advance(result, Stage.DONE, on_stage)


async def _emit(emitter: object, event_type: EventType, payload: dict[str, object]) -> None:
    emit = getattr(emitter, "emit", None)
    if emit is None:
        return
    await emit(event_type, payload=payload)
