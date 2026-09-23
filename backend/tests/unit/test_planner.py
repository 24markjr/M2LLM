"""Phase 7 — the planner and its DAG validator.

The validator carries most of the weight here. Plan validity has to be a property of the
system rather than a hope about the model, so these tests feed it deliberately malformed
plans and require that every one is caught with a specific code.
"""

from __future__ import annotations

import pytest

from app.intelligence.planner.engine import (
    CandidatePlan,
    CandidateTask,
    PlanInvalidError,
    Planner,
    execution_levels,
)
from app.intelligence.planner.validator import find_cycle, repair, uncovered_operations, validate
from app.llm.echo import EchoProvider
from app.schemas.intent import Intent, Operation, RequiredOperation
from app.schemas.objective import Objective
from app.schemas.plan import Plan, RepairAction, ViolationCode
from app.schemas.task import Task, TaskDependency, TaskType

MAX = 20


def _task(n: int, ttype: TaskType, deps: list[str] | None = None) -> Task:
    return Task(
        task_id=f"task_{n:03d}",
        task_type=ttype,
        description=ttype.value,
        depends_on=deps or [],
    )


def _intent(*ops: Operation) -> Intent:
    return Intent(
        goal="investigate_consistency",
        objective="Check consistency.",
        required_operations=[RequiredOperation(operation=op) for op in ops]
        or [RequiredOperation(operation=Operation.SUMMARIZE)],
    )


def _valid_tasks() -> list[Task]:
    return [
        _task(1, TaskType.EXTRACT_TIMELINE),
        _task(2, TaskType.EXTRACT_BUDGET),
        _task(3, TaskType.COMPARE_SOURCES, ["task_001", "task_002"]),
        _task(4, TaskType.SYNTHESIZE, ["task_003"]),
    ]


# --- cycle detection -----------------------------------------------------------


def test_a_valid_dag_has_no_cycle() -> None:
    assert find_cycle(_valid_tasks()) == []


def test_a_two_node_cycle_is_detected_with_its_path() -> None:
    """Reporting the path makes the failure diagnosable in one read."""
    tasks = [
        _task(1, TaskType.EXTRACT_TIMELINE, ["task_002"]),
        _task(2, TaskType.EXTRACT_BUDGET, ["task_001"]),
        _task(3, TaskType.SYNTHESIZE, ["task_001"]),
    ]
    cycle = find_cycle(tasks)
    assert cycle, "a cycle must be detected"
    assert cycle[0] == cycle[-1], "the path must be reported as a closed loop"


def test_a_longer_cycle_is_detected() -> None:
    tasks = [
        _task(1, TaskType.EXTRACT_TIMELINE, ["task_003"]),
        _task(2, TaskType.EXTRACT_BUDGET, ["task_001"]),
        _task(3, TaskType.COMPARE_SOURCES, ["task_002"]),
        _task(4, TaskType.SYNTHESIZE, ["task_003"]),
    ]
    assert find_cycle(tasks)


def test_a_diamond_is_not_a_cycle() -> None:
    """Two independent paths that reconverge are legal and common."""
    tasks = [
        _task(1, TaskType.PROCESS_DOCUMENTS),
        _task(2, TaskType.EXTRACT_TIMELINE, ["task_001"]),
        _task(3, TaskType.EXTRACT_BUDGET, ["task_001"]),
        _task(4, TaskType.SYNTHESIZE, ["task_002", "task_003"]),
    ]
    assert find_cycle(tasks) == []


# --- validation: every malformed plan is caught --------------------------------


def test_a_well_formed_plan_passes() -> None:
    result = validate(_valid_tasks(), _intent(Operation.COMPARE_SOURCES), max_tasks=MAX)
    assert result.valid
    assert result.clean


def test_an_empty_plan_is_rejected() -> None:
    result = validate([], _intent(), max_tasks=MAX)
    assert not result.valid
    assert result.violations[0].code is ViolationCode.EMPTY_PLAN


def test_a_cycle_is_reported_as_a_violation() -> None:
    tasks = [
        _task(1, TaskType.EXTRACT_TIMELINE, ["task_002"]),
        _task(2, TaskType.EXTRACT_BUDGET, ["task_001"]),
        _task(3, TaskType.SYNTHESIZE, ["task_001"]),
    ]
    result = validate(tasks, _intent(), max_tasks=MAX)
    codes = {v.code for v in result.violations}
    assert ViolationCode.CYCLE in codes
    cycle_violation = next(v for v in result.violations if v.code is ViolationCode.CYCLE)
    assert cycle_violation.path, "the offending path must be recorded"


def test_a_dangling_dependency_is_caught() -> None:
    tasks = [
        _task(1, TaskType.EXTRACT_TIMELINE, ["task_999"]),
        _task(2, TaskType.SYNTHESIZE, ["task_001"]),
    ]
    result = validate(tasks, _intent(), max_tasks=MAX)
    assert ViolationCode.DANGLING_DEPENDENCY in {v.code for v in result.violations}


def test_a_self_dependency_is_caught() -> None:
    task = _task(1, TaskType.EXTRACT_TIMELINE)
    # Bypass the model validator to simulate what a planner might emit.
    object.__setattr__(task, "depends_on", ["task_001"])
    result = validate([task, _task(2, TaskType.SYNTHESIZE)], _intent(), max_tasks=MAX)
    assert ViolationCode.SELF_DEPENDENCY in {v.code for v in result.violations}


def test_a_plan_with_no_terminal_task_is_rejected() -> None:
    """Without a terminal task nothing consumes the analysis and no report is produced."""
    tasks = [
        _task(1, TaskType.EXTRACT_TIMELINE),
        _task(2, TaskType.EXTRACT_BUDGET, ["task_001"]),
    ]
    result = validate(tasks, _intent(), max_tasks=MAX)
    assert ViolationCode.NO_TERMINAL_TASK in {v.code for v in result.violations}


def test_an_orphan_task_is_caught() -> None:
    """A non-terminal task nothing depends on burns budget and is discarded."""
    tasks = [
        _task(1, TaskType.EXTRACT_TIMELINE),
        _task(2, TaskType.EXTRACT_BUDGET),  # nothing consumes this
        _task(3, TaskType.SYNTHESIZE, ["task_001"]),
    ]
    result = validate(tasks, _intent(), max_tasks=MAX)
    orphan = next(v for v in result.violations if v.code is ViolationCode.ORPHAN_TASK)
    assert "task_002" in orphan.task_ids


def test_an_oversized_plan_is_rejected() -> None:
    tasks = [_task(i, TaskType.EXTRACT_TIMELINE) for i in range(1, 6)]
    tasks.append(_task(6, TaskType.SYNTHESIZE, [f"task_{i:03d}" for i in range(1, 6)]))
    result = validate(tasks, _intent(), max_tasks=3)
    assert ViolationCode.PLAN_TOO_LARGE in {v.code for v in result.violations}


def test_an_uncovered_operation_is_a_violation() -> None:
    """This is what stops the planner quietly dropping half the request."""
    tasks = _valid_tasks()
    result = validate(
        tasks, _intent(Operation.COMPARE_SOURCES, Operation.VERIFY_FINDINGS), max_tasks=MAX
    )
    assert ViolationCode.UNCOVERED_OPERATION in {v.code for v in result.violations}
    assert Operation.VERIFY_FINDINGS in result.uncovered_operations


def test_optional_operations_do_not_have_to_be_covered() -> None:
    intent = Intent(
        goal="g",
        objective="o",
        required_operations=[
            RequiredOperation(operation=Operation.COMPARE_SOURCES),
            RequiredOperation(operation=Operation.ASSESS_IMPACT, optional=True),
        ],
    )
    assert uncovered_operations(_valid_tasks(), intent) == []


# --- repairs: deterministic and recorded ---------------------------------------


def test_a_self_loop_is_repaired_and_recorded() -> None:
    task = _task(1, TaskType.EXTRACT_TIMELINE)
    object.__setattr__(task, "depends_on", ["task_001"])
    tasks, _, repairs = repair([task, _task(2, TaskType.SYNTHESIZE, ["task_001"])], MAX)

    assert tasks[0].depends_on == []
    assert repairs[0].action is RepairAction.BROKE_SELF_LOOP


def test_a_duplicate_edge_is_repaired() -> None:
    task = _task(2, TaskType.SYNTHESIZE)
    object.__setattr__(task, "depends_on", ["task_001", "task_001"])
    tasks, _, repairs = repair([_task(1, TaskType.EXTRACT_TIMELINE), task], MAX)

    assert tasks[1].depends_on == ["task_001"]
    assert repairs[0].action is RepairAction.DROPPED_DUPLICATE_EDGE


def test_a_dangling_edge_is_repaired() -> None:
    tasks, _, repairs = repair(
        [
            _task(1, TaskType.EXTRACT_TIMELINE, ["task_999"]),
            _task(2, TaskType.SYNTHESIZE, ["task_001"]),
        ],
        MAX,
    )
    assert tasks[0].depends_on == []
    assert repairs[0].action is RepairAction.DROPPED_DANGLING_EDGE


def test_repairs_build_the_dependency_edge_list() -> None:
    _, dependencies, _ = repair(_valid_tasks(), MAX)
    pairs = {(d.depends_on_task_id, d.task_id) for d in dependencies}
    assert ("task_001", "task_003") in pairs
    assert ("task_002", "task_003") in pairs


def test_a_clean_plan_records_no_repairs() -> None:
    """Phase 20 counts plans that pass with zero repairs, not plans that were rescued."""
    _, _, repairs = repair(_valid_tasks(), MAX)
    assert repairs == []


# --- execution waves -----------------------------------------------------------


def test_independent_tasks_land_in_the_same_wave() -> None:
    """What makes the parallelism in a plan visible rather than theoretical."""
    plan = Plan(
        tasks=_valid_tasks(),
        dependencies=[
            TaskDependency(task_id="task_003", depends_on_task_id="task_001"),
            TaskDependency(task_id="task_003", depends_on_task_id="task_002"),
            TaskDependency(task_id="task_004", depends_on_task_id="task_003"),
        ],
    )
    levels = execution_levels(plan)

    assert levels[0] == ["task_001", "task_002"], "the two extractions are independent"
    assert levels[1] == ["task_003"]
    assert levels[2] == ["task_004"]


def test_a_fully_serial_plan_has_one_task_per_wave() -> None:
    plan = Plan(
        tasks=[
            _task(1, TaskType.EXTRACT_TIMELINE),
            _task(2, TaskType.COMPARE_SOURCES, ["task_001"]),
            _task(3, TaskType.SYNTHESIZE, ["task_002"]),
        ]
    )
    assert [len(level) for level in execution_levels(plan)] == [1, 1, 1]


# --- the planner end to end (on EchoProvider) ----------------------------------


def _plan_json(*tasks: tuple[str, str, list[str]]) -> str:
    import json

    return json.dumps(
        {
            "tasks": [
                {"id": tid, "type": ttype, "description": ttype, "depends_on": deps}
                for tid, ttype, deps in tasks
            ]
        }
    )


async def test_planner_produces_a_validated_plan() -> None:
    provider = EchoProvider(
        responses={
            "planner": [
                _plan_json(
                    ("task_001", "extract_timeline", []),
                    ("task_002", "extract_budget", []),
                    ("task_003", "compare_sources", ["task_001", "task_002"]),
                    ("task_004", "synthesize", ["task_003"]),
                )
            ]
        }
    )
    plan = await Planner(provider).create_plan(
        _intent(Operation.COMPARE_SOURCES), Objective(text="Compare the sources.")
    )

    assert len(plan.tasks) == 4
    assert plan.validation is not None and plan.validation.valid
    assert plan.validation.clean


async def test_an_invented_task_type_is_dropped_and_surfaces_as_uncovered() -> None:
    """An invented type becomes a specific violation rather than vanishing silently."""
    provider = EchoProvider(
        responses={
            "planner": [
                _plan_json(
                    ("task_001", "hack_the_mainframe", []),
                    ("task_002", "synthesize", []),
                )
            ]
        }
    )
    with pytest.raises(PlanInvalidError) as exc_info:
        await Planner(provider).create_plan(
            _intent(Operation.COMPARE_SOURCES), Objective(text="Compare.")
        )
    assert ViolationCode.UNCOVERED_OPERATION in {v.code for v in exc_info.value.result.violations}


async def test_an_invalid_plan_is_re_prompted_with_the_reasons() -> None:
    """Specific errors fix far more than 'try again' - the same principle as the
    structured-output repair loop."""
    provider = EchoProvider(
        responses={
            "planner": [
                _plan_json(("task_001", "extract_timeline", [])),  # no terminal task
                _plan_json(
                    ("task_001", "compare_sources", []),
                    ("task_002", "synthesize", ["task_001"]),
                ),
            ]
        }
    )
    plan = await Planner(provider).create_plan(
        _intent(Operation.COMPARE_SOURCES), Objective(text="Compare.")
    )

    assert plan.validation is not None
    assert plan.validation.valid
    assert not plan.validation.clean, "a rescued plan is valid but not clean"
    assert plan.validation.reprompt_count == 1
    assert "terminal" in provider.calls[1].prompt


async def test_a_persistently_invalid_plan_fails_cleanly() -> None:
    """Executing a bad plan is never an option: a cycle would hang the scheduler."""
    provider = EchoProvider(
        responses={"planner": [_plan_json(("task_001", "extract_timeline", []))]}
    )
    with pytest.raises(PlanInvalidError):
        await Planner(provider).create_plan(_intent(), Objective(text="Do something."))


async def test_plan_creation_is_recorded_on_the_timeline() -> None:
    from app.core.events import EventBus, MemoryEventSink, RunEventEmitter
    from app.schemas.common import new_run_id
    from app.schemas.event import EventType

    memory = MemoryEventSink()
    emitter = RunEventEmitter(EventBus([memory]), new_run_id())
    provider = EchoProvider(
        responses={
            "planner": [
                _plan_json(
                    ("task_001", "compare_sources", []),
                    ("task_002", "synthesize", ["task_001"]),
                )
            ]
        }
    )

    await Planner(provider).create_plan(
        _intent(Operation.COMPARE_SOURCES), Objective(text="Compare."), emit=emitter
    )

    created = memory.of_type(EventType.PLAN_CREATED)
    assert len(created) == 1
    assert created[0].payload["task_count"] == 2
    assert created[0].payload["clean"] is True
    assert memory.of_type(EventType.TASK_GRAPH_CREATED)


def test_candidate_plan_accepts_an_empty_task_list() -> None:
    """A model failure degrades to an empty candidate, which the validator then rejects."""
    assert CandidatePlan().tasks == []
    assert CandidateTask().type == ""
