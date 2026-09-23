"""Run state: everything the agent knows at a given moment.

`ExecutionState` is the object the replanning loop reads and mutates. It is deliberately a
plain data container — the intelligence lives in the engines, not in the state. That split
is what lets Phase 20 reconstruct a run from persisted state and recompute its metrics
without re-running anything.
"""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum

from pydantic import Field

from app.schemas.common import (
    JarvisModel,
    JsonDict,
    RunId,
    TaskId,
    new_run_id,
    utcnow,
)
from app.schemas.evidence import Evidence, EvidenceGap
from app.schemas.finding import Finding
from app.schemas.intent import Intent
from app.schemas.objective import Objective
from app.schemas.plan import Plan, PlanRevision
from app.schemas.task import Task, TaskStatus


class RunStatus(StrEnum):
    PENDING = "PENDING"
    RUNNING = "RUNNING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"
    # Finished within its bounds, but with unresolved gaps. An honest outcome, and a
    # different one from COMPLETED — the report says so.
    COMPLETED_WITH_GAPS = "COMPLETED_WITH_GAPS"


class RunPhase(StrEnum):
    """Where the run is. Drives the UI phase tracker."""

    UNDERSTANDING = "UNDERSTANDING"
    PLANNING = "PLANNING"
    EXECUTING = "EXECUTING"
    REASONING = "REASONING"
    VERIFYING = "VERIFYING"
    REPLANNING = "REPLANNING"
    SYNTHESIZING = "SYNTHESIZING"
    DONE = "DONE"


class TerminationReason(StrEnum):
    """Why the adaptive loop stopped. Every stop records one.

    A loop that stops silently is indistinguishable from a loop that gave up, and
    `DIMINISHING_RETURNS` in particular is a *good* outcome worth showing: it means the
    agent recognised that another iteration was not worth the cost.
    """

    ALL_RESOLVED = "ALL_RESOLVED"
    MAX_ITERATIONS = "MAX_ITERATIONS"
    NO_ACTIONABLE_GAP = "NO_ACTIONABLE_GAP"
    BUDGET_EXHAUSTED = "BUDGET_EXHAUSTED"
    DIMINISHING_RETURNS = "DIMINISHING_RETURNS"
    CANCELLED = "CANCELLED"


class Observation(JarvisModel):
    """What came back from executing one task, in the form reasoning consumes.

    Distinct from `TaskResult`: a result is the tool's raw return, an observation is the
    run's memory of it. Compaction (Phase 12) may summarise `content` when context grows —
    but never `sources`, because a summary that loses its sources cannot support anything.
    """

    task_id: TaskId
    task_type: str
    content: str = ""
    structured: JsonDict = Field(default_factory=dict)
    sources: list[str] = Field(default_factory=list)
    # Set when the content has been compacted, so reasoning knows it is reading a summary.
    compacted: bool = False
    recorded_at: datetime = Field(default_factory=utcnow)


class Budget(JarvisModel):
    """Consumption against the run's ceilings."""

    tool_calls_used: int = Field(default=0, ge=0)
    tool_calls_limit: int = Field(default=40, ge=1)
    llm_calls_used: int = Field(default=0, ge=0)
    elapsed_s: float = Field(default=0.0, ge=0)
    wallclock_limit_s: float = Field(default=600.0, gt=0)

    @property
    def tool_calls_remaining(self) -> int:
        return max(0, self.tool_calls_limit - self.tool_calls_used)

    @property
    def exhausted(self) -> bool:
        return (
            self.tool_calls_used >= self.tool_calls_limit
            or self.elapsed_s >= self.wallclock_limit_s
        )


class ExecutionState(JarvisModel):
    """The complete state of one run."""

    run_id: RunId = Field(default_factory=new_run_id)
    objective: Objective
    status: RunStatus = RunStatus.PENDING
    current_phase: RunPhase = RunPhase.UNDERSTANDING

    intent: Intent | None = None
    plan: Plan | None = None
    tasks: list[Task] = Field(default_factory=list)

    observations: list[Observation] = Field(default_factory=list)
    evidence: list[Evidence] = Field(default_factory=list)
    findings: list[Finding] = Field(default_factory=list)
    gaps: list[EvidenceGap] = Field(default_factory=list)

    revisions: list[PlanRevision] = Field(default_factory=list)
    replan_iteration: int = Field(default=0, ge=0)
    termination_reason: TerminationReason | None = None

    budget: Budget = Field(default_factory=Budget)

    created_at: datetime = Field(default_factory=utcnow)
    started_at: datetime | None = None
    completed_at: datetime | None = None

    # --- Task views ------------------------------------------------------------

    def task(self, task_id: TaskId) -> Task | None:
        return next((t for t in self.tasks if t.task_id == task_id), None)

    def tasks_with_status(self, status: TaskStatus) -> list[Task]:
        return [t for t in self.tasks if t.status is status]

    @property
    def completed_tasks(self) -> list[Task]:
        return self.tasks_with_status(TaskStatus.COMPLETED)

    @property
    def has_pending_work(self) -> bool:
        return any(not t.is_terminal and t.status is not TaskStatus.FAILED for t in self.tasks)

    # --- Finding views ---------------------------------------------------------

    @property
    def verified_findings(self) -> list[Finding]:
        return [f for f in self.findings if f.is_verified]

    @property
    def rejected_findings(self) -> list[Finding]:
        """Contradicted by the evidence. Shown in the report, not hidden."""
        return [f for f in self.findings if f.is_rejected]

    @property
    def uncertain_findings(self) -> list[Finding]:
        return [f for f in self.findings if not f.is_verified and not f.is_rejected]

    @property
    def findings_needing_investigation(self) -> list[Finding]:
        """What the replanning loop should work on next."""
        return [f for f in self.findings if f.needs_investigation]

    @property
    def unresolved_gaps(self) -> list[EvidenceGap]:
        return [g for g in self.gaps if not g.resolved]

    # --- Metrics the evaluation harness reads ----------------------------------

    @property
    def evidence_coverage(self) -> float:
        """Share of findings with at least one resolved evidence reference."""
        if not self.findings:
            return 0.0
        supported = sum(1 for f in self.findings if f.has_resolved_evidence)
        return supported / len(self.findings)

    @property
    def mean_confidence(self) -> float:
        if not self.findings:
            return 0.0
        return sum(f.confidence.value for f in self.findings) / len(self.findings)

    def evidence_by_id(self, evidence_id: str) -> Evidence | None:
        return next((e for e in self.evidence if e.evidence_id == evidence_id), None)
