"""Repositories — the only code that touches a database session.

Engines talk to repositories, never to sessions. That keeps persistence out of the
cognitive loop: the replanning controller does not know whether its findings are being
stored, and would behave identically either way.
"""

from __future__ import annotations

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.logging import get_logger
from app.models.tables import (
    AgentRun,
    Evidence,
    EvidenceGap,
    ExecutionEvent,
    Finding,
    Task,
    TaskDependency,
    ToolExecution,
    Verification,
)
from app.schemas.event import ExecutionEvent as EventSchema
from app.schemas.evidence import EvidenceGap as GapSchema
from app.schemas.execution import ExecutionState
from app.schemas.finding import Finding as FindingSchema
from app.schemas.task import Task as TaskSchema

log = get_logger(__name__)


class RunRepository:
    """Runs, and the tasks and findings that belong to them."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create(self, state: ExecutionState, *, model: str = "") -> AgentRun:
        run = AgentRun(
            id=state.run_id,
            objective=state.objective.text,
            status=state.status.value,
            current_phase=state.current_phase.value,
            model=model,
            intent=state.intent.model_dump(mode="json") if state.intent else None,
            created_at=state.created_at,
            started_at=state.started_at,
        )
        self._session.add(run)
        await self._session.flush()
        return run

    async def get(self, run_id: str) -> AgentRun | None:
        return await self._session.get(AgentRun, run_id)

    async def list_recent(self, limit: int = 25) -> list[AgentRun]:
        result = await self._session.execute(
            select(AgentRun).order_by(AgentRun.created_at.desc()).limit(limit)
        )
        return list(result.scalars())

    async def finish(
        self,
        state: ExecutionState,
        *,
        final_result: dict[str, object] | None = None,
    ) -> None:
        run = await self.get(state.run_id)
        if run is None:
            return
        run.status = state.status.value
        run.current_phase = state.current_phase.value
        run.completed_at = state.completed_at
        run.replan_iterations = state.replan_iteration
        run.tool_calls_used = state.budget.tool_calls_used
        run.final_result = final_result
        if state.termination_reason is not None:
            run.termination_reason = state.termination_reason.value

    async def delete(self, run_id: str) -> None:
        """Remove a run and everything it produced. Cascades handle the rest."""
        await self._session.execute(delete(AgentRun).where(AgentRun.id == run_id))


class TaskRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def save_all(self, run_id: str, tasks: list[TaskSchema]) -> None:
        """Persist the task graph, including the edges that make it a DAG."""
        for task in tasks:
            row = Task(
                run_id=run_id,
                task_id=task.task_id,
                task_type=task.task_type.value,
                description=task.description,
                status=task.status.value,
                inputs=task.inputs,
                output=task.result.output if task.result else None,
                selected_tool=task.selection.tool_name if task.selection else "",
                selection_mode=task.selection.mode.value if task.selection else "",
                attempts=task.attempts,
                failure_class=(
                    task.result.failure_class.value
                    if task.result and task.result.failure_class
                    else None
                ),
                error_message=task.result.error_message if task.result else "",
                created_by_revision=task.created_by_revision,
                created_for_gap_id=task.created_for_gap_id,
                created_at=task.created_at,
                completed_at=task.completed_at,
            )
            self._session.add(row)
            await self._session.flush()

            for dependency in task.depends_on:
                self._session.add(TaskDependency(task_pk=row.id, depends_on_task_id=dependency))

    async def for_run(self, run_id: str) -> list[Task]:
        """Tasks with their edges eagerly loaded.

        A caller reading a task graph always wants the edges, and lazy-loading them would
        attempt IO after the session has closed.
        """
        result = await self._session.execute(
            select(Task)
            .where(Task.run_id == run_id)
            .options(selectinload(Task.dependencies))
            .order_by(Task.task_id)
        )
        return list(result.scalars())


class FindingRepository:
    """Findings with their evidence, verification and gaps.

    Unresolved evidence is stored alongside resolved: keeping only what resolved would make
    every stored finding look better supported than it was.
    """

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def save_all(self, run_id: str, findings: list[FindingSchema]) -> None:
        for finding in findings:
            row = Finding(
                run_id=run_id,
                finding_id=finding.finding_id,
                claim=finding.claim,
                classification=finding.classification.value,
                confidence=finding.confidence.value,
                resolution_rate=finding.confidence.resolution_rate,
                evidence_strength=finding.confidence.evidence_strength,
                source_agreement=finding.confidence.source_agreement,
                revision=finding.revision,
                created_at=finding.created_at,
            )
            self._session.add(row)
            await self._session.flush()

            for ref in finding.evidence:
                self._session.add(
                    Evidence(
                        finding_pk=row.id,
                        document_id=ref.locator.document_id,
                        locator=ref.as_ref(),
                        page=ref.locator.page,
                        row=ref.locator.row,
                        resolution=ref.resolution.value,
                        resolution_note=ref.resolution_note,
                    )
                )

            if finding.verification is not None:
                self._session.add(
                    Verification(
                        finding_pk=row.id,
                        status=finding.verification.status.value,
                        confidence=finding.verification.confidence,
                        verifier=finding.verification.verifier,
                        degraded=finding.verification.degraded,
                        degraded_reason=finding.verification.degraded_reason,
                        issues=[i.model_dump(mode="json") for i in finding.verification.issues],
                    )
                )

            for gap in finding.gaps:
                self._session.add(self._gap_row(row.id, gap))

    @staticmethod
    def _gap_row(finding_pk: int, gap: GapSchema) -> EvidenceGap:
        return EvidenceGap(
            finding_pk=finding_pk,
            gap_id=gap.gap_id,
            gap_type=gap.gap_type.value,
            missing=gap.missing,
            severity=gap.severity,
            suggested_query=gap.suggested_query,
            resolved=gap.resolved,
            resolved_by_task_id=gap.resolved_by_task_id,
        )

    async def for_run(self, run_id: str) -> list[Finding]:
        """Findings with evidence, verification and gaps eagerly loaded.

        A finding without its evidence is the exact thing this project exists to prevent,
        so the read never returns one that would need a second trip to explain itself.
        """
        result = await self._session.execute(
            select(Finding)
            .where(Finding.run_id == run_id)
            .options(
                selectinload(Finding.evidence),
                selectinload(Finding.verifications),
                selectinload(Finding.gaps),
            )
            .order_by(Finding.finding_id)
        )
        return list(result.scalars())


class EventRepository:
    """The append-only run timeline. Inserts only - no update, no delete."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def append(self, event: EventSchema) -> None:
        self._session.add(
            ExecutionEvent(
                event_id=event.event_id,
                run_id=event.run_id,
                event_type=event.event_type.value,
                t_offset_ms=event.t_offset_ms,
                payload=event.payload,
                task_id=event.task_id,
                finding_id=event.finding_id,
                tool_name=event.tool_name,
                revision=event.revision,
                timestamp=event.timestamp,
            )
        )

    async def append_many(self, events: list[EventSchema]) -> None:
        for event in events:
            await self.append(event)

    async def for_run(
        self, run_id: str, *, after_offset_ms: int | None = None
    ) -> list[ExecutionEvent]:
        """Events in timeline order. `after_offset_ms` serves SSE reconnection."""
        query = select(ExecutionEvent).where(ExecutionEvent.run_id == run_id)
        if after_offset_ms is not None:
            query = query.where(ExecutionEvent.t_offset_ms > after_offset_ms)
        result = await self._session.execute(query.order_by(ExecutionEvent.t_offset_ms))
        return list(result.scalars())


class ToolExecutionRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def record(
        self,
        run_id: str,
        task_id: str,
        *,
        call_id: str,
        tool_name: str,
        arguments: dict[str, object],
        output: dict[str, object],
        ok: bool,
        failure_class: str | None = None,
        sources: list[str] | None = None,
        execution_time_ms: int = 0,
    ) -> None:
        self._session.add(
            ToolExecution(
                run_id=run_id,
                task_id=task_id,
                call_id=call_id,
                tool_name=tool_name,
                arguments=arguments,
                output=output,
                ok=ok,
                failure_class=failure_class,
                sources=sources or [],
                execution_time_ms=execution_time_ms,
            )
        )

    async def for_run(self, run_id: str) -> list[ToolExecution]:
        result = await self._session.execute(
            select(ToolExecution).where(ToolExecution.run_id == run_id).order_by(ToolExecution.id)
        )
        return list(result.scalars())
