"""The execution engine — dependency-aware, concurrent, fault-tolerant.

The scheduler loop is deliberately simple: take everything currently ready, run it
concurrently up to the parallelism ceiling, record what happened, repeat. Complexity lives
in the *policies* around it — retry, fallback, budget — where it can be tested in isolation.

Three behaviours matter more than throughput:

**Ordering is enforced, not assumed.** `ready_tasks()` decides what may run, and the runner
asserts it again before dispatch. "No task ran before its dependencies completed" is a
property with two independent guards.

**Failures are classified, not caught.** Transient failures retry with backoff. Permanent
ones do not - retrying a schema violation burns budget to produce the identical error. When
retries are exhausted the router's fallback chain is tried, and only then is the task
skipped with a recorded reason.

**Degradation is never silent.** A skipped task, an exhausted budget and a blocked branch
each leave a trace event. A run that quietly did less than it appeared to is worse than one
that failed.
"""

from __future__ import annotations

import asyncio
import time

from app.core.agent_config import get_agent_bounds
from app.core.logging import get_logger
from app.intelligence.graph.task_graph import TaskGraph
from app.intelligence.router.engine import NoCapableToolError, ToolRouter
from app.schemas.common import FailureClass, is_retryable
from app.schemas.event import EventType
from app.schemas.execution import Budget, Observation
from app.schemas.task import Task, TaskResult, TaskStatus
from app.schemas.tool import ToolCall, ToolError, ToolResult
from app.tools.base import Tool, ToolContext, ToolRegistry

log = get_logger(__name__)


class ExecutionEngine:
    """Runs a task graph to completion, or to an honest stopping point."""

    def __init__(
        self,
        graph: TaskGraph,
        registry: ToolRegistry,
        router: ToolRouter,
        *,
        emit: object | None = None,
    ) -> None:
        self._graph = graph
        self._registry = registry
        self._router = router
        self._emit = emit

        bounds = get_agent_bounds()
        self._max_parallel = bounds.max_parallel_tasks
        self._max_attempts = bounds.max_task_retries + 1
        self.budget = Budget(
            tool_calls_limit=bounds.max_tool_calls_per_run,
            wallclock_limit_s=bounds.wallclock_limit_s,
        )

        self.observations: list[Observation] = []
        self._cancelled = False
        self._started = time.perf_counter()

    def cancel(self) -> None:
        """Cooperative cancellation, honoured between scheduling waves."""
        self._cancelled = True

    async def run(self, ctx: ToolContext) -> list[Observation]:
        """Execute until nothing is runnable, the budget is spent, or cancellation."""
        while self._graph.has_runnable_work() and not self._cancelled:
            self.budget.elapsed_s = time.perf_counter() - self._started
            if self.budget.exhausted:
                await self._event(EventType.BUDGET_WARNING, payload={"reason": "exhausted"})
                break

            wave = self._graph.ready_tasks()[: self._max_parallel]
            if not wave:
                break

            for task in wave:
                self._graph.mark(task.task_id, TaskStatus.READY)

            results = await asyncio.gather(
                *(self._run_task(task, ctx) for task in wave),
                return_exceptions=True,
            )

            for task, result in zip(wave, results, strict=True):
                if isinstance(result, BaseException):
                    # A runner should never raise; if one does the task fails rather than
                    # the run, so an unexpected bug cannot abandon the investigation.
                    log.error("task_runner_raised", task_id=task.task_id, error=str(result))
                    await self._fail(task, FailureClass.INTERNAL_ERROR, str(result))

        if self._cancelled:
            await self._event(EventType.RUN_CANCELLED)
        return self.observations

    async def _run_task(self, task: Task, ctx: ToolContext) -> None:
        # Second, independent guard on ordering.
        incomplete = [
            dep
            for dep in task.depends_on
            if (d := self._graph.get(dep)) is None or d.status is not TaskStatus.COMPLETED
        ]
        if incomplete:
            raise RuntimeError(f"{task.task_id} dispatched with incomplete deps: {incomplete}")

        try:
            selection = await self._router.route(task, emit=self._emit)
        except NoCapableToolError:
            await self._skip(task, "no registered tool serves this capability")
            return

        task.selection = selection
        tried: set[str] = set()
        tool_name = selection.tool_name

        while True:
            self._graph.mark(task.task_id, TaskStatus.RUNNING)
            task.attempts += 1
            await self._event(EventType.TASK_STARTED, task=task, tool=tool_name)

            result = await self._execute_tool(tool_name, task, ctx)
            tried.add(tool_name)

            if result.ok:
                await self._complete(task, result)
                return

            failure = result.error.failure_class if result.error else FailureClass.INTERNAL_ERROR
            message = result.error.message if result.error else "unknown failure"
            await self._event(
                EventType.TOOL_FAILED,
                task=task,
                tool=tool_name,
                payload={"failure": failure.value, "message": message[:200]},
            )

            # Transient and retries left: back off and try the same tool again.
            if is_retryable(failure) and task.attempts < self._max_attempts:
                self._graph.mark(task.task_id, TaskStatus.FAILED)
                self._graph.mark(task.task_id, TaskStatus.RETRYING)
                await self._event(EventType.TASK_RETRYING, task=task, tool=tool_name)
                await asyncio.sleep(min(2.0 ** (task.attempts - 1), 8.0))
                continue

            # Permanent, or retries exhausted: walk the fallback chain.
            fallback = self._next_fallback(task, tried)
            if fallback is not None:
                self._graph.mark(task.task_id, TaskStatus.FAILED)
                self._graph.mark(task.task_id, TaskStatus.RETRYING)
                tool_name = fallback
                await self._event(
                    EventType.TASK_RETRYING,
                    task=task,
                    tool=tool_name,
                    payload={"reason": "fallback"},
                )
                continue

            await self._fail(task, failure, message)
            return

    def _next_fallback(self, task: Task, tried: set[str]) -> str | None:
        """Another tool serving the same capability that has not been tried."""
        for tool in self._registry.serving(task.required_capability):
            if tool.name not in tried:
                return tool.name
        return None

    async def _execute_tool(self, tool_name: str, task: Task, ctx: ToolContext) -> ToolResult:
        tool = self._registry.get(tool_name)
        call = ToolCall(tool_name=tool_name, arguments=self._arguments(task, tool, ctx))

        if tool is None:
            return ToolResult(
                call_id=call.call_id,
                tool_name=tool_name,
                ok=False,
                error=ToolError(
                    failure_class=FailureClass.NO_CAPABLE_TOOL,
                    message=f"tool '{tool_name}' is not registered",
                ),
            )

        self.budget.tool_calls_used += 1
        task_ctx = ctx.model_copy(update={"task_id": task.task_id})

        try:
            return await asyncio.wait_for(tool.execute(call, task_ctx), timeout=tool.timeout_s)
        except TimeoutError:
            return ToolResult(
                call_id=call.call_id,
                tool_name=tool_name,
                ok=False,
                error=ToolError(
                    failure_class=FailureClass.TIMEOUT,
                    message=f"{tool_name} exceeded {tool.timeout_s}s",
                ),
            )

    @staticmethod
    def _arguments(task: Task, tool: Tool | None, ctx: ToolContext) -> dict[str, object]:
        """Build tool arguments, keeping only fields the tool actually declares.

        The engine offers a pool of plausible values derived from the task and lets the
        tool's schema decide what it wants. Passing everything would fail validation, since
        every schema is `extra="forbid"` - and loosening that to make this easier would give
        up the protection that makes the structured-output repair loop work.
        """
        offered: dict[str, object] = dict(task.inputs)
        offered.setdefault("query", task.description or task.task_type.value)
        offered.setdefault("pattern", task.task_type.value)
        offered.setdefault("document_ids", list(ctx.document_ids))
        # A tabular tool needs one document. Prefer a CSV when the run has one.
        tabular = next((d for d in ctx.document_ids if d.endswith(".csv")), None)
        if tabular or ctx.document_ids:
            offered.setdefault("document_id", tabular or ctx.document_ids[0])

        if tool is None:
            return offered

        accepted = set(tool.input_schema.model_fields)
        return {key: value for key, value in offered.items() if key in accepted}

    # --- outcomes --------------------------------------------------------------

    async def _complete(self, task: Task, result: ToolResult) -> None:
        self._graph.mark(task.task_id, TaskStatus.COMPLETED)
        task.result = TaskResult(
            task_id=task.task_id,
            ok=True,
            output=result.output,
            sources=result.sources,
            tool_call_ids=[result.call_id],
            execution_time_ms=result.execution_time_ms,
        )
        observation = Observation(
            task_id=task.task_id,
            task_type=task.task_type.value,
            content=_summarize(result),
            structured=result.output,
            sources=result.sources,
        )
        self.observations.append(observation)
        await self._event(
            EventType.TASK_COMPLETED,
            task=task,
            tool=result.tool_name,
            payload={"sources": len(result.sources)},
        )
        await self._event(
            EventType.OBSERVATION_RECORDED,
            task=task,
            payload={"sources": observation.sources[:5]},
        )

    async def _fail(self, task: Task, failure: FailureClass, message: str) -> None:
        if task.status is not TaskStatus.FAILED:
            self._graph.mark(task.task_id, TaskStatus.FAILED)
        task.result = TaskResult(
            task_id=task.task_id, ok=False, failure_class=failure, error_message=message
        )
        await self._event(EventType.TASK_FAILED, task=task, payload={"failure": failure.value})
        blocked = self._graph.block_descendants(task.task_id)
        for task_id in blocked:
            await self._event(
                EventType.TASK_BLOCKED, payload={"task_id": task_id, "cause": task.task_id}
            )

    async def _skip(self, task: Task, reason: str) -> None:
        """Skip with a recorded reason. Never a silent drop."""
        self._graph.mark(task.task_id, TaskStatus.SKIPPED)
        await self._event(EventType.TASK_SKIPPED, task=task, payload={"reason": reason})

    async def _event(
        self,
        event_type: EventType,
        *,
        task: Task | None = None,
        tool: str | None = None,
        payload: dict[str, object] | None = None,
    ) -> None:
        if self._emit is None:
            return
        emitter = getattr(self._emit, "emit", None)
        if emitter is None:
            return
        await emitter(
            event_type,
            payload=payload or {},
            task_id=task.task_id if task else None,
            tool_name=tool,
        )


def _summarize(result: ToolResult) -> str:
    """A short, factual description of what a tool returned.

    Facts only - counts and values. Interpretation is the reasoning engine's job (Phase 13),
    and blurring that line here would let unexamined inference into the observation record.
    """
    output = result.output
    if "passages" in output:
        return f"{len(output['passages'])} matching passage(s)"
    if "extractions" in output:
        kinds: dict[str, int] = {}
        for item in output["extractions"]:
            kinds[item["kind"]] = kinds.get(item["kind"], 0) + 1
        detail = ", ".join(f"{count} {kind}(s)" for kind, count in sorted(kinds.items()))
        return detail or "no extractions"
    if "value" in output:
        return f"computed {output['value']}"
    if "rows" in output:
        total = output.get("total")
        return f"{output['rows']} row(s)" + (f", total {total}" if total is not None else "")
    return "completed"
