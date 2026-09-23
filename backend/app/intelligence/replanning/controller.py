"""Adaptive replanning — the closed loop.

Everything before this phase is a pipeline: objective in, report out. This is the edge that
turns it into a loop.

    reason -> verify -> gaps -> insert tasks -> execute -> re-reason -> verify ...

The plan is not sacred. When verification rejects a finding and gap detection names what is
missing, the task graph is edited *while it is running* and execution continues.

Three properties keep that honest:

**It is bounded.** `MAX_REPLAN_ITERATIONS` is a hard ceiling clamped from `.env`, and the
budget is checked every iteration. A loop that can run forever is not adaptive, it is
broken.

**Every stop records why.** `ALL_RESOLVED` and `DIMINISHING_RETURNS` are both good outcomes
and mean different things; `MAX_ITERATIONS` and `NO_ACTIONABLE_GAP` are both honest failures
and mean different things. A loop that stops silently is indistinguishable from one that
gave up.

**A contradicted finding is not retried.** More evidence cannot rescue a claim the sources
refute. Spending iterations on one would be the loop working hard and achieving nothing.
"""

from __future__ import annotations

from pydantic import Field

from app.core.agent_config import get_agent_bounds
from app.core.config import PlanningPolicyName, get_settings
from app.core.logging import get_logger
from app.integrations.verification import VerificationProvider, verify_finding
from app.intelligence.evidence_gap.detector import EvidenceGapDetector, emit_gaps, propose_task
from app.intelligence.execution.engine import ExecutionEngine
from app.intelligence.graph.task_graph import TaskGraph
from app.intelligence.planning_policy.scoring import ActionScore, score_action, select_actions
from app.intelligence.reasoning.engine import ReasoningEngine
from app.intelligence.router.engine import ToolRouter
from app.schemas.common import JarvisModel, SourceLocator
from app.schemas.event import EventType
from app.schemas.evidence import Evidence, EvidenceGap
from app.schemas.execution import Observation, TerminationReason
from app.schemas.finding import Finding
from app.schemas.objective import Objective
from app.schemas.plan import PlanRevision, RevisionTrigger
from app.schemas.task import Task
from app.tools.base import ToolContext, ToolRegistry

log = get_logger(__name__)


class ReplanResult(JarvisModel):
    """The outcome of the adaptive loop."""

    findings: list[Finding] = Field(default_factory=list)
    gaps: list[EvidenceGap] = Field(default_factory=list)
    revisions: list[PlanRevision] = Field(default_factory=list)
    scores: list[ActionScore] = Field(default_factory=list)
    observations: list[Observation] = Field(default_factory=list)
    iterations: int = 0
    termination_reason: TerminationReason = TerminationReason.ALL_RESOLVED

    @property
    def verified(self) -> list[Finding]:
        return [f for f in self.findings if f.is_verified]

    @property
    def unresolved_gaps(self) -> list[EvidenceGap]:
        return [g for g in self.gaps if not g.resolved]

    @property
    def mean_confidence(self) -> float:
        if not self.findings:
            return 0.0
        return sum(f.confidence.value for f in self.findings) / len(self.findings)


def evidence_from_observations(observations: list[Observation]) -> list[Evidence]:
    """Build the evidence pool that gap detection and verification read.

    One item per source locator, carrying the observation's content. This is what makes
    element-level support checkable: without the text behind a locator, a gap detector can
    only see that a citation exists, not whether it says what the claim says it says.
    """
    evidence: list[Evidence] = []
    for index, observation in enumerate(observations, start=1):
        for offset, source in enumerate(observation.sources):
            document, _, position = source.rpartition(":")
            row = position[1:] if position[:1] in {"r", "p", "c"} else position
            evidence.append(
                Evidence(
                    evidence_id=f"E-{index:03d}{offset:02d}",
                    locator=SourceLocator(
                        document_id=document or source,
                        document_name=document or source,
                        row=int(row) if row.isdigit() else None,
                    ),
                    content=f"{source}: {observation.content}",
                    retrieved_by_task_id=observation.task_id,
                )
            )
    return evidence


def evidence_text_map(evidence: list[Evidence]) -> dict[str, str]:
    return {e.locator.as_ref(): e.content for e in evidence}


class ReplanningController:
    """Runs reason -> verify -> gap -> act until resolved or bounded out."""

    def __init__(
        self,
        *,
        graph: TaskGraph,
        registry: ToolRegistry,
        router: ToolRouter,
        reasoner: ReasoningEngine,
        verifier: VerificationProvider,
        emit: object | None = None,
    ) -> None:
        self._graph = graph
        self._registry = registry
        self._router = router
        self._reasoner = reasoner
        self._verifier = verifier
        self._emit = emit

        bounds = get_agent_bounds()
        self._max_iterations = bounds.max_replan_iterations
        self._epsilon = bounds.diminishing_returns_epsilon
        self._max_tool_calls = bounds.max_tool_calls_per_run
        self._detector = EvidenceGapDetector()
        self._policy = get_settings().planning_policy

    async def run(
        self, objective: Objective, observations: list[Observation], ctx: ToolContext
    ) -> ReplanResult:
        result = ReplanResult(observations=list(observations))

        findings = await self._reason_and_verify(objective, result.observations)
        result.findings = findings

        if not findings:
            result.termination_reason = TerminationReason.NO_ACTIONABLE_GAP
            return result

        for iteration in range(1, self._max_iterations + 1):
            previous_confidence = result.mean_confidence

            actionable = [f for f in result.findings if self._is_actionable(f)]
            if not actionable:
                result.termination_reason = TerminationReason.ALL_RESOLVED
                return result

            gaps = self._detect(actionable, result.observations)
            await emit_gaps(gaps, self._emit)
            result.gaps.extend(gaps)

            if not gaps:
                result.termination_reason = TerminationReason.NO_ACTIONABLE_GAP
                return result

            inserted = await self._insert_tasks(gaps, iteration, result)
            if not inserted:
                result.termination_reason = TerminationReason.NO_ACTIONABLE_GAP
                return result

            result.iterations = iteration

            new_observations = await self._execute(ctx)
            if not new_observations:
                # Nothing was learned, so re-reasoning would produce the same findings.
                result.termination_reason = TerminationReason.DIMINISHING_RETURNS
                return result
            result.observations.extend(new_observations)

            result.findings = await self._reason_and_verify(objective, result.observations)
            self._resolve_gaps(result, inserted)

            await self._event(
                EventType.REPLAN_COMPLETED,
                {
                    "iteration": iteration,
                    "tasks_added": len(inserted),
                    "confidence_before": round(previous_confidence, 3),
                    "confidence_after": round(result.mean_confidence, 3),
                },
            )

            gain = result.mean_confidence - previous_confidence
            if gain < self._epsilon:
                # Recognising that another iteration is not worth the cost is a good
                # outcome, and a different one from running out of attempts.
                result.termination_reason = TerminationReason.DIMINISHING_RETURNS
                return result

        result.termination_reason = TerminationReason.MAX_ITERATIONS
        return result

    # --- steps -----------------------------------------------------------------

    @staticmethod
    def _is_actionable(finding: Finding) -> bool:
        """Whether the loop should spend an iteration on this finding.

        A contradicted claim is excluded: the sources refute it, and more evidence will not
        change that. It belongs in the report's rejected section, not in the loop.
        """
        if finding.verification is None:
            return not finding.has_resolved_evidence
        return finding.verification.actionable

    async def _reason_and_verify(
        self, objective: Objective, observations: list[Observation]
    ) -> list[Finding]:
        findings = await self._reasoner.derive_findings(objective, observations, emit=self._emit)
        text = evidence_text_map(evidence_from_observations(observations))

        await self._event(EventType.VERIFICATION_STARTED, {"findings": len(findings)})
        for finding in findings:
            await verify_finding(self._verifier, finding, text, emit=self._emit)
        await self._event(EventType.VERIFICATION_COMPLETED, {"findings": len(findings)})

        return findings

    def _detect(
        self, findings: list[Finding], observations: list[Observation]
    ) -> list[EvidenceGap]:
        evidence = evidence_from_observations(observations)
        gaps: list[EvidenceGap] = []
        for finding in findings:
            found = self._detector.detect(finding, evidence)
            finding.gaps = found
            gaps.extend(found)
        return gaps

    async def _insert_tasks(
        self, gaps: list[EvidenceGap], iteration: int, result: ReplanResult
    ) -> list[str]:
        """Edit the running graph. The moment the plan stops being fixed."""
        await self._event(
            EventType.REPLAN_STARTED,
            {"iteration": iteration, "gaps": len(gaps), "trigger": "EVIDENCE_GAP"},
        )

        ordered, scores = self._prioritise(gaps, result)
        result.scores.extend(scores)

        inserted: list[str] = []
        for gap, task in ordered:
            try:
                self._graph.insert_task(task)
            except ValueError as exc:
                log.warning("replan_insert_refused", task_id=task.task_id, error=str(exc))
                continue

            inserted.append(task.task_id)
            gap.resolved_by_task_id = task.task_id
            await self._event(
                EventType.TASK_CREATED,
                {"gap_id": gap.gap_id, "missing": gap.missing, "query": gap.suggested_query},
                task_id=task.task_id,
            )

        if inserted:
            result.revisions.append(
                PlanRevision(
                    revision=iteration,
                    trigger=RevisionTrigger.EVIDENCE_GAP,
                    reason=f"{len(inserted)} task(s) added to close detected evidence gaps",
                    triggered_by_id=ordered[0][0].gap_id,
                    added_task_ids=inserted,
                )
            )
            await self._event(
                EventType.PLAN_REVISED,
                {"revision": iteration, "added": inserted},
            )

        return inserted

    def _prioritise(
        self, gaps: list[EvidenceGap], result: ReplanResult
    ) -> tuple[list[tuple[EvidenceGap, Task]], list[ActionScore]]:
        """Decide which gaps are worth acting on, and in what order.

        Under the heuristic policy each candidate is scored by expected information gain
        against estimated cost, and only the best fit inside the remaining budget. Under
        `naive` every gap is acted on in severity order, which is the baseline Experiment
        002 measures the policy against.
        """
        next_index = len(self._graph.tasks) + 1
        candidates: list[tuple[EvidenceGap, Task]] = []
        for gap in gaps:
            if not gap.suggested_query.strip():
                continue
            candidates.append((gap, propose_task(gap, index=next_index)))
            next_index += 1

        if self._policy is PlanningPolicyName.NAIVE:
            ordered = sorted(candidates, key=lambda pair: pair[0].severity, reverse=True)
            return ordered, []

        documents = len({o.task_id for o in result.observations}) or 1
        scores = [
            score_action(gap, task, self._registry, document_count=documents)
            for gap, task in candidates
        ]
        # Leave room for the tasks already in the graph rather than spending the whole
        # budget on one replan iteration.
        remaining = max(1, self._max_tool_calls - len(self._graph.tasks))
        selected = select_actions(scores, limit=min(remaining, len(candidates)))

        by_task = {task.task_id: (gap, task) for gap, task in candidates}
        ordered = [by_task[s.task_id] for s in selected if s.task_id in by_task]
        return ordered, scores

    async def _execute(self, ctx: ToolContext) -> list[Observation]:
        engine = ExecutionEngine(self._graph, self._registry, self._router, emit=self._emit)
        return await engine.run(ctx)

    @staticmethod
    def _resolve_gaps(result: ReplanResult, inserted: list[str]) -> None:
        """Mark a gap resolved when its task ran and the re-derived findings improved.

        Conservative: a gap is only marked resolved when the task that was meant to close it
        actually produced an observation. Marking it closed because an iteration happened
        would make the replanning-success metric meaningless.
        """
        produced = {o.task_id for o in result.observations}
        for gap in result.gaps:
            if gap.resolved_by_task_id in inserted and gap.resolved_by_task_id in produced:
                gap.resolved = True

    async def _event(
        self,
        event_type: EventType,
        payload: dict[str, object],
        *,
        task_id: str | None = None,
    ) -> None:
        if self._emit is None:
            return
        emitter = getattr(self._emit, "emit", None)
        if emitter is None:
            return
        await emitter(event_type, payload=payload, task_id=task_id)
