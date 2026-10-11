"""Phase 49: visible adaptive planning - every task says why it is in the plan.

Rationales come from what put a task there - the objective's operations, a repair, an evidence gap,
the knowledge pass - never from a model; the plan tree groups tasks into workstreams and lists every
change with its reason.
"""

from __future__ import annotations

import json

from app.api.plan_tree import plan_tree
from app.intelligence.planner.engine import Planner
from app.intelligence.planner.rationale import (
    ANALYSE,
    EXTRACT,
    GAPS,
    PURPOSE,
    REPORT,
    WORKSTREAMS,
    annotate,
    rationale_for,
)
from app.intelligence.planner.validator import cover_operations, repair
from app.llm.echo import EchoProvider
from app.orchestration.mission import MissionResult
from app.schemas.common import new_run_id
from app.schemas.execution import Observation
from app.schemas.intent import Intent, Operation, RequiredOperation
from app.schemas.objective import AttachedDocument, Objective, ObjectiveScope
from app.schemas.plan import Plan, PlanRevision, RevisionTrigger
from app.schemas.task import Task, TaskStatus, TaskType


def _intent(*ops: Operation) -> Intent:
    return Intent(
        goal="investigate_consistency",
        objective="Compare the reports.",
        required_operations=[RequiredOperation(operation=op) for op in ops],
    )


def _task(n: int, task_type: TaskType, deps: list[str] | None = None, **extra: object) -> Task:
    return Task.model_validate(
        {
            "task_id": f"task_{n:03d}",
            "task_type": task_type,
            "description": task_type.value,
            "depends_on": deps or [],
            **extra,
        }
    )


def test_every_task_type_has_a_purpose_and_a_workstream() -> None:
    """A new task type without them fails here, not in front of a reader."""
    assert set(PURPOSE) == set(TaskType)
    assert set(WORKSTREAMS) == set(TaskType)


def test_a_planned_task_names_the_operation_the_objective_asked_for() -> None:
    task = _task(1, TaskType.COMPARE_SOURCES)
    assert rationale_for(task, _intent(Operation.COMPARE_SOURCES)) == (
        "the objective asks to compare_sources; this sets the sources against each other"
    )
    assert rationale_for(task, _intent(Operation.EXTRACT_TIMELINE)) == (
        "this sets the sources against each other"
    )


def test_a_reason_already_given_is_kept() -> None:
    tasks = [
        _task(1, TaskType.RETRIEVE_EVIDENCE, rationale="closes gap G-1", created_for_gap_id="G-1")
    ]
    annotate(tasks, None)
    assert tasks[0].rationale == "closes gap G-1"
    assert tasks[0].workstream == GAPS


def test_repairs_say_why_they_added_a_step() -> None:
    tasks, _, _ = repair([_task(1, TaskType.EXTRACT_TIMELINE)], max_tasks=10)
    assert tasks[-1].task_type is TaskType.SYNTHESIZE
    assert tasks[-1].rationale == "added by a repair: every plan must end in its report"

    covered = cover_operations(
        [_task(1, TaskType.EXTRACT_TIMELINE), _task(2, TaskType.SYNTHESIZE, ["task_001"])],
        [Operation.DETECT_INCONSISTENCIES, Operation.DETECT_CONTRADICTIONS],
        20,
    )
    assert covered is not None
    assert covered[0][-1].rationale == (
        "added by a repair: the objective requires detect_inconsistencies, detect_contradictions "
        "and the planner left it out on every attempt"
    )


async def test_every_planned_task_has_a_rationale() -> None:
    """The invariant: no task in a plan without a reason."""
    plan_json = json.dumps(
        {
            "tasks": [
                {
                    "id": "task_001",
                    "type": "extract_timeline",
                    "description": "x",
                    "depends_on": [],
                },
                {
                    "id": "task_002",
                    "type": "compare_sources",
                    "description": "y",
                    "depends_on": ["task_001"],
                },
            ]
        }
    )
    plan = await Planner(EchoProvider(responses={"planner": [plan_json]})).create_plan(
        _intent(Operation.EXTRACT_TIMELINE, Operation.COMPARE_SOURCES), Objective(text="Compare.")
    )
    assert all(t.rationale for t in plan.tasks)
    assert all(t.workstream for t in plan.tasks)
    assert plan.tasks[0].workstream == EXTRACT
    assert plan.tasks[-1].workstream == REPORT


def test_the_tree_groups_steps_and_lists_each_change_with_its_reason() -> None:
    tasks = [
        _task(1, TaskType.EXTRACT_TIMELINE, status=TaskStatus.COMPLETED),
        _task(2, TaskType.COMPARE_SOURCES, ["task_001"], status=TaskStatus.COMPLETED),
        _task(3, TaskType.SYNTHESIZE, ["task_002"], status=TaskStatus.COMPLETED),
        _task(
            4,
            TaskType.RETRIEVE_EVIDENCE,
            ["task_002"],
            status=TaskStatus.COMPLETED,
            created_by_revision=1,
            created_for_gap_id="G-001",
            rationale="inserted by the replanning loop to close gap G-001: the approved baseline",
        ),
    ]
    annotate(tasks, _intent(Operation.EXTRACT_TIMELINE, Operation.COMPARE_SOURCES))
    run_id = new_run_id()
    result = MissionResult(
        run_id=run_id,
        objective=Objective(
            text="Compare the reports.",
            scope=ObjectiveScope(documents=[AttachedDocument(document_id="a.txt", name="a.txt")]),
        ),
        plan=Plan(tasks=tasks),
        observations=[
            Observation(task_id="task_001", task_type="extract_timeline", content="4 date(s)")
        ],
        revisions=[
            PlanRevision(
                revision=1,
                trigger=RevisionTrigger.EVIDENCE_GAP,
                reason="1 task(s) added to close detected evidence gaps",
                triggered_by_id="G-001",
                added_task_ids=["task_004"],
                tasks_before=["task_001", "task_002", "task_003"],
                tasks_after=["task_001", "task_002", "task_003", "task_004"],
            )
        ],
    )

    tree = plan_tree(run_id, result)

    assert [w.name for w in tree.workstreams] == [EXTRACT, ANALYSE, GAPS, "Verify and report"]
    first = tree.workstreams[0].steps[0]
    assert first.inputs == ["the documents (1)"]
    assert first.output == "4 date(s)"
    compare = tree.workstreams[1].steps[0]
    assert compare.why.startswith("the objective asks to compare_sources")
    assert compare.inputs[0].startswith("task_001 ")
    [change] = tree.changes
    assert (change.reason, change.triggered_by) == (
        "1 task(s) added to close detected evidence gaps",
        "G-001",
    )
    assert (change.tasks_before, change.tasks_after) == (3, 4)
    assert change.added[0].why.endswith("the approved baseline")
