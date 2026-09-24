"""Plan validation — where the model's proposal becomes an executable plan, or does not.

This module is the clearest statement of the project's central design position: **the model
proposes; the system disposes.** Plan validity is a property of the system, not a hope about
the model.

Every violation found and every repair applied is recorded, and both are persisted. That
record is not bookkeeping — it is the evidence behind the Phase 20 "plan validity" metric,
which counts plans that pass *with zero repairs*. A system that silently fixed bad plans
would score perfectly while the model quietly got worse.

Repairs are deliberately boring: drop a duplicate edge, break a self-loop, drop an edge to a
task that does not exist. Anything requiring judgement goes back to the model rather than
being guessed at here.
"""

from __future__ import annotations

from app.core.logging import get_logger
from app.schemas.intent import Intent, Operation
from app.schemas.plan import (
    PlanRepair,
    PlanValidationResult,
    PlanViolation,
    RepairAction,
    ViolationCode,
)
from app.schemas.task import TASK_SATISFIES, Task, TaskDependency, TaskType

log = get_logger(__name__)

# Task types that legitimately terminate a plan - nothing needs to consume their output.
TERMINAL_TYPES: frozenset[TaskType] = frozenset(
    {TaskType.SYNTHESIZE, TaskType.VERIFY_FINDINGS, TaskType.SUMMARIZE}
)


def find_cycle(tasks: list[Task]) -> list[str]:
    """Return the offending path if the graph has a cycle, else an empty list.

    Reports the *path*, not merely the fact. `task_004 -> task_006 -> task_004` is
    diagnosable in one read; "this plan has a cycle" is not.

    Three-colour DFS: white = unvisited, grey = on the current stack, black = finished.
    Reaching a grey node means the stack from that node to here is the cycle.
    """
    edges: dict[str, list[str]] = {t.task_id: list(t.depends_on) for t in tasks}
    colour: dict[str, int] = dict.fromkeys(edges, 0)
    stack: list[str] = []

    def visit(node: str) -> list[str]:
        colour[node] = 1
        stack.append(node)
        for parent in edges.get(node, []):
            if parent not in colour:
                continue  # dangling edge; reported separately
            if colour[parent] == 1:
                start = stack.index(parent)
                return [*stack[start:], parent]
            if colour[parent] == 0:
                found = visit(parent)
                if found:
                    return found
        colour[node] = 2
        stack.pop()
        return []

    for node in edges:
        if colour[node] == 0:
            cycle = visit(node)
            if cycle:
                return cycle
    return []


def repair(
    tasks: list[Task], max_tasks: int
) -> tuple[list[Task], list[TaskDependency], list[PlanRepair]]:
    """Apply deterministic fixes before spending a re-prompt.

    Cheap and safe only. A repair that guessed at intent would hide a planner problem behind
    a plausible-looking plan, which is exactly what the validity metric exists to detect.
    """
    repairs: list[PlanRepair] = []
    known = {t.task_id for t in tasks}
    fixed: list[Task] = []

    for task in tasks:
        deps = task.depends_on

        if task.task_id in deps:
            deps = [d for d in deps if d != task.task_id]
            repairs.append(
                PlanRepair(
                    action=RepairAction.BROKE_SELF_LOOP,
                    detail=f"{task.task_id} depended on itself",
                    task_ids=[task.task_id],
                )
            )

        if len(set(deps)) != len(deps):
            seen: list[str] = []
            for d in deps:
                if d not in seen:
                    seen.append(d)
            repairs.append(
                PlanRepair(
                    action=RepairAction.DROPPED_DUPLICATE_EDGE,
                    detail=f"{task.task_id} listed a dependency more than once",
                    task_ids=[task.task_id],
                )
            )
            deps = seen

        dangling = [d for d in deps if d not in known]
        if dangling:
            deps = [d for d in deps if d in known]
            repairs.append(
                PlanRepair(
                    action=RepairAction.DROPPED_DANGLING_EDGE,
                    detail=f"{task.task_id} depended on unknown task(s): {dangling}",
                    task_ids=[task.task_id],
                )
            )

        fixed.append(task.model_copy(update={"depends_on": deps}))

    # Truncate at the cap, but reserve a slot when the plan has no terminal task. The cap
    # counts the investigating work; the report is not optional, and a plan that fills every
    # slot with extraction and produces nothing has spent the whole budget for no output.
    # Without this reservation the model - which emits exactly as many tasks as it is
    # allowed - leaves no room for the repair below, and the run fails instead of shrinking.
    fixed = fixed[:max_tasks]
    if max_tasks > 1 and not any(t.task_type in TERMINAL_TYPES for t in fixed):
        fixed = fixed[: max_tasks - 1]

    # A plan with no terminal task produces no report, and the model omits one often enough
    # that re-prompting does not reliably fix it - measured: lowering the requested plan size
    # made it omit the terminal task on every attempt, so the run failed outright rather than
    # producing a smaller plan.
    #
    # Appending one requires no judgement. The type is fixed and what it consumes is every
    # leaf the plan already has, which is the same rule the orphan repair uses. It runs before
    # that repair so newly orphaned tasks are connected to the task just added.
    if fixed and not any(t.task_type in TERMINAL_TYPES for t in fixed):
        if len(fixed) < max_tasks:
            depended_on = {d for t in fixed for d in t.depends_on}
            leaves = [t.task_id for t in fixed if t.task_id not in depended_on]
            appended = Task(
                task_id=f"task_{len(fixed) + 1:03d}",
                task_type=TaskType.SYNTHESIZE,
                description="Synthesize the findings into the final report",
                depends_on=leaves,
            )
            fixed.append(appended)
            repairs.append(
                PlanRepair(
                    action=RepairAction.APPENDED_TERMINAL_TASK,
                    detail=(
                        f"the plan had no terminal task; {appended.task_id} was added, "
                        f"consuming {leaves}"
                    ),
                    task_ids=[appended.task_id],
                )
            )
        else:
            # At the cap with no terminal task, appending would mean dropping one of the
            # planner's tasks to make room - a judgement call, so it goes back to the model
            # as a violation instead of being guessed at here.
            log.warning("no_terminal_task_and_no_room_to_append", tasks=len(fixed))

    # An orphan is wasteful, not unexecutable: its output is produced and then discarded.
    # Rejecting the whole plan over one would throw away good work, and small models emit
    # them persistently enough that re-prompting does not reliably fix it. Connecting the
    # orphan to the terminal task preserves the work instead of discarding it, and is a
    # deterministic fix requiring no judgement.
    terminal = next((t for t in reversed(fixed) if t.task_type in TERMINAL_TYPES), None)
    if terminal is not None:
        depended_on = {d for t in fixed for d in t.depends_on}
        orphans = [
            t.task_id
            for t in fixed
            if t.task_id not in depended_on
            and t.task_type not in TERMINAL_TYPES
            and t.task_id != terminal.task_id
        ]
        if orphans:
            terminal.depends_on = list(dict.fromkeys([*terminal.depends_on, *orphans]))
            repairs.append(
                PlanRepair(
                    action=RepairAction.CONNECTED_ORPHAN,
                    detail=f"{terminal.task_id} now consumes {orphans}",
                    task_ids=orphans,
                )
            )

    dependencies = [
        TaskDependency(task_id=t.task_id, depends_on_task_id=d) for t in fixed for d in t.depends_on
    ]
    return fixed, dependencies, repairs


def validate(
    tasks: list[Task],
    intent: Intent,
    *,
    max_tasks: int,
    min_tasks: int = 2,
    reprompt_count: int = 0,
) -> PlanValidationResult:
    """Check a candidate plan against every rule that makes it executable."""
    violations: list[PlanViolation] = []

    if not tasks:
        return PlanValidationResult(
            valid=False,
            violations=[
                PlanViolation(code=ViolationCode.EMPTY_PLAN, message="the plan has no tasks")
            ],
            reprompt_count=reprompt_count,
        )

    if len(tasks) < min_tasks:
        violations.append(
            PlanViolation(
                code=ViolationCode.EMPTY_PLAN,
                message=f"a plan needs at least {min_tasks} tasks, got {len(tasks)}",
            )
        )

    if len(tasks) > max_tasks:
        violations.append(
            PlanViolation(
                code=ViolationCode.PLAN_TOO_LARGE,
                message=f"a plan may have at most {max_tasks} tasks, got {len(tasks)}",
            )
        )

    ids = [t.task_id for t in tasks]
    duplicates = sorted({i for i in ids if ids.count(i) > 1})
    if duplicates:
        violations.append(
            PlanViolation(
                code=ViolationCode.DUPLICATE_TASK_ID,
                message=f"duplicate task ids: {duplicates}",
                task_ids=duplicates,
            )
        )

    known = set(ids)
    for task in tasks:
        if task.task_id in task.depends_on:
            violations.append(
                PlanViolation(
                    code=ViolationCode.SELF_DEPENDENCY,
                    message=f"{task.task_id} depends on itself",
                    task_ids=[task.task_id],
                )
            )
        for dep in task.depends_on:
            if dep not in known:
                violations.append(
                    PlanViolation(
                        code=ViolationCode.DANGLING_DEPENDENCY,
                        message=f"{task.task_id} depends on unknown task {dep}",
                        task_ids=[task.task_id],
                    )
                )

    cycle = find_cycle(tasks)
    if cycle:
        violations.append(
            PlanViolation(
                code=ViolationCode.CYCLE,
                message="dependency cycle: " + " -> ".join(cycle),
                task_ids=sorted(set(cycle)),
                path=cycle,
            )
        )

    # A plan must end somewhere. Without a terminal task nothing consumes the analysis and
    # the run produces no report.
    if not any(t.task_type in TERMINAL_TYPES for t in tasks):
        violations.append(
            PlanViolation(
                code=ViolationCode.NO_TERMINAL_TASK,
                message=(
                    "no terminal task: the plan must end in synthesize, verify_findings "
                    "or summarize"
                ),
            )
        )

    # Orphans: a non-terminal task nothing depends on. Its output is produced and then
    # discarded, which is wasted budget and usually a planning mistake.
    depended_on = {dep for t in tasks for dep in t.depends_on}
    orphans = [
        t.task_id
        for t in tasks
        if t.task_id not in depended_on and t.task_type not in TERMINAL_TYPES
    ]
    if orphans:
        violations.append(
            PlanViolation(
                code=ViolationCode.ORPHAN_TASK,
                message=f"nothing consumes the output of: {orphans}",
                task_ids=orphans,
            )
        )

    uncovered = uncovered_operations(tasks, intent)
    if uncovered:
        violations.append(
            PlanViolation(
                code=ViolationCode.UNCOVERED_OPERATION,
                message=(
                    "the plan does not cover required operation(s): "
                    + ", ".join(op.value for op in uncovered)
                ),
            )
        )

    return PlanValidationResult(
        valid=not violations,
        violations=violations,
        uncovered_operations=uncovered,
        reprompt_count=reprompt_count,
    )


def uncovered_operations(tasks: list[Task], intent: Intent) -> list[Operation]:
    """Mandatory operations from the intent that no task implements.

    This is what stops the planner quietly dropping half the request. The intent said what
    was needed; if the plan cannot deliver it, that is a violation, not a detail.
    """
    covered: set[Operation] = set()
    for task in tasks:
        covered |= TASK_SATISFIES.get(task.task_type, set())
    return [op for op in intent.mandatory_operations if op not in covered]
