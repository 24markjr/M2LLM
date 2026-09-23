"""Tasks: the nodes of the execution graph.

The state machine here is explicit rather than implied by a boolean or two. Illegal
transitions raise instead of quietly passing, because a task that moves from `PENDING`
straight to `COMPLETED` without running is exactly the kind of bug that produces a
confident report built on work that never happened.
"""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum

from pydantic import Field, model_validator

from app.schemas.common import (
    FailureClass,
    JarvisModel,
    JsonDict,
    NonEmptyStr,
    TaskId,
    utcnow,
)
from app.schemas.intent import Operation
from app.schemas.tool import ToolCapability, ToolSelection


class TaskType(StrEnum):
    """The closed vocabulary of task types.

    A plan referencing a type outside this set fails validation (Phase 7). This is the
    second half of the intent-vocabulary defence: operations the agent claims to need must
    map to task types it can actually execute.
    """

    PROCESS_DOCUMENTS = "process_documents"
    EXTRACT_TIMELINE = "extract_timeline"
    EXTRACT_BUDGET = "extract_budget"
    EXTRACT_MILESTONES = "extract_milestones"
    EXTRACT_ENTITIES = "extract_entities"
    EXTRACT_CLAIMS = "extract_claims"
    NORMALIZE_DATES = "normalize_dates"
    NORMALIZE_VALUES = "normalize_values"
    COMPARE_SOURCES = "compare_sources"
    DETECT_INCONSISTENCIES = "detect_inconsistencies"
    CALCULATE_DIFFERENCE = "calculate_difference"
    ASSESS_IMPACT = "assess_impact"
    RETRIEVE_EVIDENCE = "retrieve_evidence"
    VERIFY_FINDINGS = "verify_findings"
    SUMMARIZE = "summarize"
    SYNTHESIZE = "synthesize"


# Which capability a task type needs. The router's deterministic first stage reads this,
# which is why most routing decisions never reach a model at all.
TASK_CAPABILITY: dict[TaskType, ToolCapability] = {
    TaskType.PROCESS_DOCUMENTS: ToolCapability.DOCUMENT_EXTRACT,
    TaskType.EXTRACT_TIMELINE: ToolCapability.DOCUMENT_EXTRACT,
    TaskType.EXTRACT_BUDGET: ToolCapability.DOCUMENT_EXTRACT,
    TaskType.EXTRACT_MILESTONES: ToolCapability.DOCUMENT_EXTRACT,
    TaskType.EXTRACT_ENTITIES: ToolCapability.DOCUMENT_EXTRACT,
    TaskType.EXTRACT_CLAIMS: ToolCapability.DOCUMENT_EXTRACT,
    TaskType.NORMALIZE_DATES: ToolCapability.COMPUTATION,
    TaskType.NORMALIZE_VALUES: ToolCapability.COMPUTATION,
    TaskType.COMPARE_SOURCES: ToolCapability.DOCUMENT_SEARCH,
    TaskType.DETECT_INCONSISTENCIES: ToolCapability.DOCUMENT_SEARCH,
    TaskType.CALCULATE_DIFFERENCE: ToolCapability.COMPUTATION,
    TaskType.ASSESS_IMPACT: ToolCapability.CONTEXT_RETRIEVAL,
    TaskType.RETRIEVE_EVIDENCE: ToolCapability.EVIDENCE_RETRIEVAL,
    TaskType.VERIFY_FINDINGS: ToolCapability.VERIFICATION,
    TaskType.SUMMARIZE: ToolCapability.CONTEXT_RETRIEVAL,
    TaskType.SYNTHESIZE: ToolCapability.CONTEXT_RETRIEVAL,
}

# Which operations a task type satisfies, for the planner's intent-coverage check.
TASK_SATISFIES: dict[TaskType, set[Operation]] = {
    TaskType.PROCESS_DOCUMENTS: {Operation.PROCESS_DOCUMENTS},
    TaskType.EXTRACT_TIMELINE: {Operation.EXTRACT_TIMELINE},
    TaskType.EXTRACT_BUDGET: {Operation.EXTRACT_BUDGET},
    TaskType.EXTRACT_MILESTONES: {Operation.EXTRACT_MILESTONES},
    TaskType.EXTRACT_ENTITIES: {Operation.EXTRACT_ENTITIES},
    TaskType.EXTRACT_CLAIMS: {Operation.EXTRACT_CLAIMS},
    TaskType.NORMALIZE_DATES: {Operation.NORMALIZE_DATES},
    TaskType.NORMALIZE_VALUES: {Operation.NORMALIZE_VALUES},
    TaskType.COMPARE_SOURCES: {Operation.COMPARE_SOURCES},
    TaskType.DETECT_INCONSISTENCIES: {
        Operation.DETECT_INCONSISTENCIES,
        Operation.DETECT_CONTRADICTIONS,
    },
    TaskType.CALCULATE_DIFFERENCE: {Operation.CALCULATE_DIFFERENCE},
    TaskType.ASSESS_IMPACT: {Operation.ASSESS_IMPACT},
    TaskType.RETRIEVE_EVIDENCE: {Operation.RETRIEVE_EVIDENCE},
    TaskType.VERIFY_FINDINGS: {Operation.VERIFY_FINDINGS},
    TaskType.SUMMARIZE: {Operation.SUMMARIZE},
    TaskType.SYNTHESIZE: {Operation.GENERATE_REPORT},
}


class TaskStatus(StrEnum):
    PENDING = "PENDING"
    READY = "READY"
    RUNNING = "RUNNING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    RETRYING = "RETRYING"
    # A transitive descendant of a task that failed terminally.
    BLOCKED = "BLOCKED"
    # Made unnecessary by replanning, or impossible with no capable tool.
    SKIPPED = "SKIPPED"


# The legal state machine. Anything not listed here is a bug, and `can_transition`
# is what turns that from a silent corruption into a loud failure.
LEGAL_TRANSITIONS: dict[TaskStatus, frozenset[TaskStatus]] = {
    TaskStatus.PENDING: frozenset({TaskStatus.READY, TaskStatus.BLOCKED, TaskStatus.SKIPPED}),
    TaskStatus.READY: frozenset({TaskStatus.RUNNING, TaskStatus.BLOCKED, TaskStatus.SKIPPED}),
    TaskStatus.RUNNING: frozenset({TaskStatus.COMPLETED, TaskStatus.FAILED}),
    TaskStatus.FAILED: frozenset({TaskStatus.RETRYING, TaskStatus.SKIPPED}),
    TaskStatus.RETRYING: frozenset({TaskStatus.RUNNING, TaskStatus.FAILED, TaskStatus.SKIPPED}),
    # Terminal.
    TaskStatus.COMPLETED: frozenset(),
    TaskStatus.BLOCKED: frozenset({TaskStatus.SKIPPED}),
    TaskStatus.SKIPPED: frozenset(),
}

TERMINAL_STATUSES: frozenset[TaskStatus] = frozenset({TaskStatus.COMPLETED, TaskStatus.SKIPPED})


def can_transition(current: TaskStatus, target: TaskStatus) -> bool:
    return target in LEGAL_TRANSITIONS[current]


class IllegalTransitionError(ValueError):
    def __init__(self, task_id: str, current: TaskStatus, target: TaskStatus) -> None:
        super().__init__(f"{task_id}: illegal transition {current.value} -> {target.value}")
        self.task_id = task_id
        self.current = current
        self.target = target


class TaskDependency(JarvisModel):
    """An edge in the task graph: `task_id` cannot start until `depends_on_task_id` is done."""

    task_id: TaskId
    depends_on_task_id: TaskId

    @model_validator(mode="after")
    def _no_self_dependency(self) -> TaskDependency:
        if self.task_id == self.depends_on_task_id:
            raise ValueError(f"{self.task_id} cannot depend on itself")
        return self


class TaskResult(JarvisModel):
    """What a task produced."""

    task_id: TaskId
    ok: bool
    output: JsonDict = Field(default_factory=dict)
    # Source locators for anything retrieved, in compact `doc.pdf:p12` form.
    sources: list[str] = Field(default_factory=list)
    failure_class: FailureClass | None = None
    error_message: str = ""
    tool_call_ids: list[str] = Field(default_factory=list)
    execution_time_ms: int = Field(default=0, ge=0)

    @model_validator(mode="after")
    def _failures_are_classified(self) -> TaskResult:
        if not self.ok and self.failure_class is None:
            raise ValueError(
                "a failed task must carry a failure_class - the retry policy cannot "
                "decide transient vs. permanent without it"
            )
        return self


class Task(JarvisModel):
    """One unit of work in the graph."""

    task_id: TaskId
    task_type: TaskType
    description: NonEmptyStr = ""
    status: TaskStatus = TaskStatus.PENDING
    depends_on: list[TaskId] = Field(default_factory=list)
    inputs: JsonDict = Field(default_factory=dict)

    # Routing outcome, recorded once decided.
    selection: ToolSelection | None = None
    result: TaskResult | None = None

    attempts: int = Field(default=0, ge=0)
    max_attempts: int = Field(default=3, ge=1)

    # Provenance: replanning-inserted tasks say what caused them, so the graph can
    # explain itself. Phase 22 uses this to visually mark replan insertions.
    created_by_revision: int = Field(default=0, ge=0)
    created_for_gap_id: str | None = None

    created_at: datetime = Field(default_factory=utcnow)
    started_at: datetime | None = None
    completed_at: datetime | None = None

    @property
    def required_capability(self) -> ToolCapability:
        return TASK_CAPABILITY[self.task_type]

    @property
    def satisfies(self) -> set[Operation]:
        return TASK_SATISFIES.get(self.task_type, set())

    @property
    def is_terminal(self) -> bool:
        return self.status in TERMINAL_STATUSES

    @property
    def retries_remaining(self) -> int:
        return max(0, self.max_attempts - self.attempts)

    def transition_to(self, target: TaskStatus) -> None:
        """Move to a new state, or raise.

        Mutating status directly bypasses this check, which is why the execution engine
        routes every change through here.
        """
        if not can_transition(self.status, target):
            raise IllegalTransitionError(self.task_id, self.status, target)
        self.status = target
        if target is TaskStatus.RUNNING and self.started_at is None:
            self.started_at = utcnow()
        if target in {TaskStatus.COMPLETED, TaskStatus.FAILED, TaskStatus.SKIPPED}:
            self.completed_at = utcnow()

    @model_validator(mode="after")
    def _no_self_dependency(self) -> Task:
        if self.task_id in self.depends_on:
            raise ValueError(f"{self.task_id} lists itself as a dependency")
        if len(set(self.depends_on)) != len(self.depends_on):
            raise ValueError(f"{self.task_id} has duplicate dependencies")
        return self
