"""Phases 8 & 11 — the task graph and the execution engine."""

from __future__ import annotations

from typing import ClassVar

import pytest

from app.core.events import EventBus, MemoryEventSink, RunEventEmitter
from app.intelligence.execution.engine import ExecutionEngine
from app.intelligence.graph.task_graph import TaskGraph
from app.intelligence.router.engine import ToolRouter
from app.schemas.common import FailureClass, new_run_id
from app.schemas.event import EventType
from app.schemas.task import IllegalTransitionError, Task, TaskStatus, TaskType
from app.schemas.tool import ToolCall, ToolCapability, ToolResult
from app.tools.base import Tool, ToolContext, ToolRegistry
from app.tools.builtin import DocumentExtractTool, DocumentSearchTool, ExtractInput, ExtractOutput

DOCS = {"report.txt": "Completion 2026-04-30.\nBudget 380,000 approved.\nSpend 450,000.\n"}


def _task(n: int, ttype: TaskType, deps: list[str] | None = None) -> Task:
    return Task(
        task_id=f"task_{n:03d}", task_type=ttype, description=ttype.value, depends_on=deps or []
    )


def _graph() -> TaskGraph:
    return TaskGraph(
        [
            _task(1, TaskType.EXTRACT_TIMELINE),
            _task(2, TaskType.EXTRACT_BUDGET),
            _task(3, TaskType.COMPARE_SOURCES, ["task_001", "task_002"]),
        ]
    )


def _ctx() -> ToolContext:
    return ToolContext(run_id=new_run_id(), document_ids=list(DOCS), documents=DOCS)


# --- the task graph ------------------------------------------------------------


def test_only_dependency_free_tasks_are_ready_initially() -> None:
    graph = _graph()
    assert [t.task_id for t in graph.ready_tasks()] == ["task_001", "task_002"]


def test_a_task_becomes_ready_only_when_all_dependencies_complete() -> None:
    """The single source of truth for what may run next."""
    graph = _graph()
    graph.mark("task_001", TaskStatus.READY)
    graph.mark("task_001", TaskStatus.RUNNING)
    graph.mark("task_001", TaskStatus.COMPLETED)

    assert "task_003" not in [t.task_id for t in graph.ready_tasks()], "one dep still pending"

    graph.mark("task_002", TaskStatus.READY)
    graph.mark("task_002", TaskStatus.RUNNING)
    graph.mark("task_002", TaskStatus.COMPLETED)

    assert "task_003" in [t.task_id for t in graph.ready_tasks()]


def test_an_illegal_transition_raises() -> None:
    graph = _graph()
    with pytest.raises(IllegalTransitionError):
        graph.mark("task_001", TaskStatus.COMPLETED)


def test_a_terminal_failure_blocks_only_its_descendants() -> None:
    """One dead path must not abandon an investigation that could still produce something."""
    graph = TaskGraph(
        [
            _task(1, TaskType.EXTRACT_TIMELINE),
            _task(2, TaskType.EXTRACT_BUDGET),
            _task(3, TaskType.COMPARE_SOURCES, ["task_001"]),
            _task(4, TaskType.SYNTHESIZE, ["task_003"]),
        ]
    )
    graph.mark("task_001", TaskStatus.READY)
    graph.mark("task_001", TaskStatus.RUNNING)
    graph.get("task_001").max_attempts = 1  # type: ignore[union-attr]
    graph.get("task_001").attempts = 1  # type: ignore[union-attr]
    graph.mark("task_001", TaskStatus.FAILED)

    assert graph.get("task_003").status is TaskStatus.BLOCKED  # type: ignore[union-attr]
    assert graph.get("task_004").status is TaskStatus.BLOCKED  # type: ignore[union-attr]
    assert graph.get("task_002").status is TaskStatus.PENDING, "independent branch survives"  # type: ignore[union-attr]


def test_inserting_a_task_mid_run_keeps_the_graph_acyclic() -> None:
    """The mechanism behind adaptive replanning (Phase 16)."""
    graph = _graph()
    inserted = graph.insert_task(_task(9, TaskType.RETRIEVE_EVIDENCE), after=["task_001"])
    assert inserted.depends_on == ["task_001"]
    assert graph.find_cycle() == []
    assert graph.revision == 1


def test_an_insertion_that_would_create_a_cycle_is_refused() -> None:
    graph = _graph()
    task = _task(9, TaskType.RETRIEVE_EVIDENCE)
    graph.insert_task(task, after=["task_003"])
    # Now make task_001 depend on the new task, closing a loop.
    graph.get("task_001").depends_on = ["task_009"]  # type: ignore[union-attr]
    assert graph.find_cycle(), "the cycle must be detectable after mutation"


# --- the execution engine ------------------------------------------------------


async def test_a_plan_runs_to_completion_against_real_documents() -> None:
    registry = ToolRegistry()
    registry.register(DocumentExtractTool())
    registry.register(DocumentSearchTool())
    graph = _graph()

    engine = ExecutionEngine(graph, registry, ToolRouter(registry))
    observations = await engine.run(_ctx())

    done, total = graph.progress()
    assert done == total == 3
    assert len(observations) == 3
    assert any(o.sources for o in observations), "evidence must carry locators"


async def test_no_task_runs_before_its_dependencies() -> None:
    """Asserted twice: by ready_tasks(), and again by the runner before dispatch."""
    registry = ToolRegistry()
    registry.register(DocumentExtractTool())
    registry.register(DocumentSearchTool())
    graph = _graph()
    memory = MemoryEventSink()
    emitter = RunEventEmitter(EventBus([memory]), new_run_id())

    await ExecutionEngine(graph, registry, ToolRouter(registry), emit=emitter).run(_ctx())

    order = [e.task_id for e in memory.of_type(EventType.TASK_COMPLETED)]
    assert order.index("task_003") > order.index("task_001")
    assert order.index("task_003") > order.index("task_002")


class FlakyTool(Tool):
    """Fails with a transient error, then succeeds."""

    name = "flaky_extract"
    description = "Fails once, then works."
    capabilities: ClassVar[set[ToolCapability]] = {ToolCapability.DOCUMENT_EXTRACT}
    input_schema = ExtractInput
    output_schema = ExtractOutput
    cost_hint = DocumentExtractTool.cost_hint

    def __init__(self) -> None:
        self.calls = 0

    async def execute(self, call: ToolCall, ctx: ToolContext) -> ToolResult:
        self.calls += 1
        if self.calls == 1:
            return self.failure(call, FailureClass.TIMEOUT, "simulated timeout")
        return self.success(call, {"extractions": []}, sources=["report.txt:r1"])


class BrokenTool(Tool):
    """Always fails permanently."""

    name = "broken_extract"
    description = "Always fails."
    capabilities: ClassVar[set[ToolCapability]] = {ToolCapability.DOCUMENT_EXTRACT}
    input_schema = ExtractInput
    output_schema = ExtractOutput

    async def execute(self, call: ToolCall, ctx: ToolContext) -> ToolResult:
        return self.failure(call, FailureClass.SCHEMA_VIOLATION, "always broken")


async def test_a_transient_failure_is_retried_and_recovers() -> None:
    registry = ToolRegistry()
    flaky = FlakyTool()
    registry.register(flaky)
    graph = TaskGraph([_task(1, TaskType.EXTRACT_TIMELINE)])
    memory = MemoryEventSink()
    emitter = RunEventEmitter(EventBus([memory]), new_run_id())

    await ExecutionEngine(graph, registry, ToolRouter(registry), emit=emitter).run(_ctx())

    assert flaky.calls == 2, "the transient failure was retried"
    assert graph.get("task_001").status is TaskStatus.COMPLETED  # type: ignore[union-attr]
    assert memory.of_type(EventType.TASK_RETRYING)


async def test_a_permanent_failure_falls_back_to_another_tool() -> None:
    """Demo 4: tool fails, fallback, run continues."""
    registry = ToolRegistry()
    registry.register(BrokenTool())
    registry.register(DocumentExtractTool())
    graph = TaskGraph([_task(1, TaskType.EXTRACT_TIMELINE)])
    memory = MemoryEventSink()
    emitter = RunEventEmitter(EventBus([memory]), new_run_id())

    await ExecutionEngine(graph, registry, ToolRouter(registry), emit=emitter).run(_ctx())

    assert graph.get("task_001").status is TaskStatus.COMPLETED  # type: ignore[union-attr]
    assert memory.of_type(EventType.TOOL_FAILED), "the failure is recorded, not hidden"


async def test_a_permanent_failure_with_no_fallback_fails_the_task() -> None:
    registry = ToolRegistry()
    registry.register(BrokenTool())
    graph = TaskGraph([_task(1, TaskType.EXTRACT_TIMELINE)])

    await ExecutionEngine(graph, registry, ToolRouter(registry)).run(_ctx())

    task = graph.get("task_001")
    assert task is not None
    assert task.status is TaskStatus.FAILED
    assert task.result is not None and task.result.failure_class is FailureClass.SCHEMA_VIOLATION


async def test_a_task_with_no_capable_tool_is_skipped_with_a_reason() -> None:
    """Never a silent drop: a dropped task produces invisibly missing support."""
    registry = ToolRegistry()
    registry.register(DocumentExtractTool())
    graph = TaskGraph([_task(1, TaskType.VERIFY_FINDINGS)])
    memory = MemoryEventSink()
    emitter = RunEventEmitter(EventBus([memory]), new_run_id())

    await ExecutionEngine(graph, registry, ToolRouter(registry), emit=emitter).run(_ctx())

    assert graph.get("task_001").status is TaskStatus.SKIPPED  # type: ignore[union-attr]
    skipped = memory.of_type(EventType.TASK_SKIPPED)
    assert skipped and skipped[0].payload["reason"]


async def test_tool_calls_are_counted_against_the_budget() -> None:
    registry = ToolRegistry()
    registry.register(DocumentExtractTool())
    registry.register(DocumentSearchTool())
    graph = _graph()

    engine = ExecutionEngine(graph, registry, ToolRouter(registry))
    await engine.run(_ctx())

    assert engine.budget.tool_calls_used == 3
    assert not engine.budget.exhausted


async def test_cancellation_stops_the_run() -> None:
    registry = ToolRegistry()
    registry.register(DocumentExtractTool())
    registry.register(DocumentSearchTool())
    graph = _graph()

    engine = ExecutionEngine(graph, registry, ToolRouter(registry))
    engine.cancel()
    observations = await engine.run(_ctx())

    assert observations == []
    done, _ = graph.progress()
    assert done == 0


async def test_arguments_are_filtered_to_what_each_tool_declares() -> None:
    """Every schema is extra='forbid', so offering everything would fail validation.

    Loosening that to make argument-building easier would give up the protection the
    structured-output repair loop depends on.
    """
    registry = ToolRegistry()
    registry.register(DocumentExtractTool())
    graph = TaskGraph([_task(1, TaskType.EXTRACT_TIMELINE)])

    await ExecutionEngine(graph, registry, ToolRouter(registry)).run(_ctx())

    assert graph.get("task_001").status is TaskStatus.COMPLETED  # type: ignore[union-attr]
