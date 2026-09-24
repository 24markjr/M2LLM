"""Plans, their validation, and their revisions.

The central idea: **a plan is a candidate until the system says otherwise.** The model
proposes a decomposition; `PlanValidationResult` records every violation found and every
repair applied, and both are persisted. That record is not bookkeeping — it is the evidence
behind the Phase 20 "plan validity" metric, which measures how often plans pass *with zero
repairs*. A system that silently fixed bad plans would score perfectly while the model got
steadily worse.
"""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum

from pydantic import Field, model_validator

from app.schemas.common import JarvisModel, NonEmptyStr, Severity, TaskId, utcnow
from app.schemas.intent import Operation
from app.schemas.task import Task, TaskDependency


class ViolationCode(StrEnum):
    """Why a candidate plan is not executable.

    Each maps to a specific check in the Phase 7 validator, and each is individually
    counted, so "the planner keeps emitting cycles" is a visible fact rather than a hunch.
    """

    CYCLE = "CYCLE"
    DANGLING_DEPENDENCY = "DANGLING_DEPENDENCY"
    DUPLICATE_TASK_ID = "DUPLICATE_TASK_ID"
    UNKNOWN_TASK_TYPE = "UNKNOWN_TASK_TYPE"
    SELF_DEPENDENCY = "SELF_DEPENDENCY"
    ORPHAN_TASK = "ORPHAN_TASK"
    UNCOVERED_OPERATION = "UNCOVERED_OPERATION"
    EMPTY_PLAN = "EMPTY_PLAN"
    PLAN_TOO_LARGE = "PLAN_TOO_LARGE"
    NO_TERMINAL_TASK = "NO_TERMINAL_TASK"


class RepairAction(StrEnum):
    """Deterministic fixes applied before spending a re-prompt.

    Cheap, safe and boring on purpose. Anything requiring judgement goes back to the model
    rather than being guessed at here.
    """

    DROPPED_DUPLICATE_EDGE = "DROPPED_DUPLICATE_EDGE"
    BROKE_SELF_LOOP = "BROKE_SELF_LOOP"
    REORDERED_TASK_IDS = "REORDERED_TASK_IDS"
    DROPPED_DANGLING_EDGE = "DROPPED_DANGLING_EDGE"
    CONNECTED_ORPHAN = "CONNECTED_ORPHAN"
    APPENDED_TERMINAL_TASK = "APPENDED_TERMINAL_TASK"


class PlanViolation(JarvisModel):
    code: ViolationCode
    message: NonEmptyStr
    severity: Severity = Severity.HIGH
    task_ids: list[TaskId] = Field(default_factory=list)
    # For CYCLE, the offending path — "task_004 -> task_006 -> task_004". Reporting the
    # path rather than just the fact makes the failure diagnosable in one read.
    path: list[TaskId] = Field(default_factory=list)


class PlanRepair(JarvisModel):
    action: RepairAction
    detail: str = ""
    task_ids: list[TaskId] = Field(default_factory=list)


class PlanValidationResult(JarvisModel):
    """The verdict on a candidate plan, with its full working shown."""

    valid: bool
    violations: list[PlanViolation] = Field(default_factory=list)
    repairs: list[PlanRepair] = Field(default_factory=list)
    uncovered_operations: list[Operation] = Field(default_factory=list)
    reprompt_count: int = Field(default=0, ge=0)

    @property
    def clean(self) -> bool:
        """Valid on the first pass, with no repairs and no re-prompts.

        This is what Phase 20's plan-validity metric actually counts. `valid` after three
        repairs is a rescued plan, not a good one.
        """
        return self.valid and not self.repairs and self.reprompt_count == 0

    @model_validator(mode="after")
    def _invalid_plans_state_why(self) -> PlanValidationResult:
        if not self.valid and not self.violations:
            raise ValueError("an invalid plan must record at least one violation")
        return self


class Plan(JarvisModel):
    """A validated decomposition of an intent into tasks and dependencies."""

    tasks: list[Task] = Field(min_length=1)
    dependencies: list[TaskDependency] = Field(default_factory=list)
    validation: PlanValidationResult | None = None
    # Bumped by every replanning mutation. Revision 0 is the original plan.
    revision: int = Field(default=0, ge=0)
    created_at: datetime = Field(default_factory=utcnow)

    @property
    def task_ids(self) -> set[TaskId]:
        return {t.task_id for t in self.tasks}

    @property
    def covered_operations(self) -> set[Operation]:
        covered: set[Operation] = set()
        for t in self.tasks:
            covered |= t.satisfies
        return covered

    def task(self, task_id: TaskId) -> Task | None:
        return next((t for t in self.tasks if t.task_id == task_id), None)

    def edges(self) -> list[tuple[TaskId, TaskId]]:
        """(dependency, dependent) pairs. The form Phase 20 scores edge precision on."""
        return [(d.depends_on_task_id, d.task_id) for d in self.dependencies]

    @model_validator(mode="after")
    def _ids_are_unique(self) -> Plan:
        ids = [t.task_id for t in self.tasks]
        if len(ids) != len(set(ids)):
            dupes = sorted({i for i in ids if ids.count(i) > 1})
            raise ValueError(f"duplicate task ids: {dupes}")
        return self

    @model_validator(mode="after")
    def _dependencies_reference_real_tasks(self) -> Plan:
        known = self.task_ids
        for dep in self.dependencies:
            if dep.task_id not in known:
                raise ValueError(f"dependency references unknown task {dep.task_id}")
            if dep.depends_on_task_id not in known:
                raise ValueError(f"{dep.task_id} depends on unknown task {dep.depends_on_task_id}")
        return self


class RevisionTrigger(StrEnum):
    """Why the plan changed. Every revision records one.

    Without this the graph shows *that* it changed and never *why*, which makes the
    replanning loop impossible to audit and impossible to demonstrate convincingly.
    """

    EVIDENCE_GAP = "EVIDENCE_GAP"
    TASK_FAILURE = "TASK_FAILURE"
    INVALIDATED_ASSUMPTION = "INVALIDATED_ASSUMPTION"
    SOURCE_CONFLICT = "SOURCE_CONFLICT"


class PlanRevision(JarvisModel):
    """One mid-run change to the plan, attributable to a specific cause."""

    revision: int = Field(ge=1)
    trigger: RevisionTrigger
    reason: NonEmptyStr
    # What prompted it: a gap id, a failed task id.
    triggered_by_id: str = ""
    added_task_ids: list[TaskId] = Field(default_factory=list)
    skipped_task_ids: list[TaskId] = Field(default_factory=list)
    added_dependencies: list[TaskDependency] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=utcnow)

    @model_validator(mode="after")
    def _a_revision_must_change_something(self) -> PlanRevision:
        if not (self.added_task_ids or self.skipped_task_ids or self.added_dependencies):
            raise ValueError("a plan revision that changes nothing should not have been recorded")
        return self
