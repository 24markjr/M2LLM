"""Mission routes.

Every handler reads from the registry and shapes a response. None of them runs the pipeline:
a mission is started as a background task and the request returns a run id immediately,
because an investigation takes a minute or more and a request that waits for one times out.

Nothing here blocks on the agent, and nothing here reaches into a model. Invariant 1 holds
at this layer for free - the API has no LLM dependency at all, only the orchestrator does.
"""

from __future__ import annotations

from fastapi import APIRouter, Query, Request, Response, status
from fastapi.responses import PlainTextResponse

from app.api.errors import ApiError, MissionNotFinishedError, MissionNotFoundError
from app.api.registry import MissionRecord, get_registry
from app.api.v1.schemas import (
    CancelResponse,
    CreateMissionRequest,
    EventPage,
    EventRecord,
    FindingsResponse,
    GapRecord,
    MissionDetail,
    MissionSummary,
    TaskGraphResponse,
    TaskNode,
)
from app.api.v1.stream import stream_mission
from app.core.logging import get_logger
from app.intelligence.planner.engine import execution_levels
from app.intelligence.synthesis.renderers import to_markdown
from app.llm import get_provider
from app.orchestration.mission import MissionStatus
from app.schemas.objective import AttachedDocument, DocumentKind, Objective, ObjectiveScope
from app.schemas.result import FinalReport
from app.tools.loader import load_by_name

log = get_logger(__name__)
router = APIRouter(prefix="/missions", tags=["missions"])


# --- creating and listing -------------------------------------------------------


@router.post("", response_model=MissionDetail, status_code=status.HTTP_202_ACCEPTED)
async def create_mission(body: CreateMissionRequest) -> MissionDetail:
    """Start a mission. 202, not 201: the work is accepted, not finished."""
    registry = get_registry()

    if registry.at_capacity:
        # Refusing is more honest than queueing silently. A local model serves one request
        # at a time, so an accepted-but-queued mission would sit at PENDING with no
        # indication of why, and look identical to one that had hung.
        raise ApiError(
            "AT_CAPACITY",
            "too many missions are already running; retry when one finishes",
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
        )

    documents, loaded = load_by_name(body.documents)
    missing = [name for name in body.documents if name not in documents]
    if body.documents and not documents:
        raise ApiError(
            "NO_READABLE_DOCUMENTS",
            "none of the attached documents could be read",
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            details={"requested": body.documents},
        )
    if missing:
        # The run proceeds on what was readable, and says what it excluded. Silently
        # investigating a subset would let a partial read pass for a full one.
        log.warning("documents_excluded", missing=missing)

    record = registry.create(
        objective=_objective(body),
        documents=sorted(documents),
        loaded=documents,
        page_starts={d.document_id: d.page_starts for d in loaded if d.page_starts},
        provider=get_provider(),
    )
    return _detail(record)


@router.get("", response_model=list[MissionSummary])
async def list_missions(limit: int = Query(default=50, ge=1, le=200)) -> list[MissionSummary]:
    return [_summary(r) for r in get_registry().records()[:limit]]


@router.get("/{run_id}", response_model=MissionDetail)
async def get_mission(run_id: str) -> MissionDetail:
    return _detail(_require(run_id))


# --- what the run is doing ------------------------------------------------------


@router.get("/{run_id}/tasks", response_model=TaskGraphResponse)
async def get_tasks(run_id: str) -> TaskGraphResponse:
    """The task graph with live statuses, plus the waves that can run concurrently."""
    record = _require(run_id)
    plan = record.result.plan if record.result else None
    if plan is None:
        raise MissionNotFinishedError(run_id, "task graph", record.stage.value)

    nodes = [
        TaskNode(
            task_id=task.task_id,
            task_type=task.task_type,
            description=task.description,
            status=task.status,
            depends_on=list(task.depends_on),
            tool_id=task.selection.tool_name if task.selection else "",
            inserted_by_replan=task.created_by_revision > 0,
        )
        for task in plan.tasks
    ]
    edges = [(dep, task.task_id) for task in plan.tasks for dep in task.depends_on]
    return TaskGraphResponse(run_id=run_id, nodes=nodes, edges=edges, waves=execution_levels(plan))


@router.get("/{run_id}/events", response_model=EventPage)
async def get_events(
    run_id: str,
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=200, ge=1, le=1000),
) -> EventPage:
    """The full event log, paginated. This is the run's reconstructable record."""
    record = _require(run_id)
    window = record.events[offset : offset + limit]
    return EventPage(
        run_id=run_id,
        events=[
            EventRecord(
                event_id=e.event_id,
                event_type=e.event_type.value,
                t_offset_ms=e.t_offset_ms,
                task_id=e.task_id,
                finding_id=e.finding_id,
                payload=dict(e.payload),
            )
            for e in window
        ],
        total=len(record.events),
        offset=offset,
        limit=limit,
    )


@router.get("/{run_id}/findings", response_model=FindingsResponse)
async def get_findings(run_id: str) -> FindingsResponse:
    record = _require(run_id)
    findings = record.result.findings if record.result else []
    return FindingsResponse(run_id=run_id, findings=findings)


@router.get("/{run_id}/gaps", response_model=list[GapRecord])
async def get_gaps(run_id: str) -> list[GapRecord]:
    record = _require(run_id)
    gaps = record.result.gaps if record.result else []
    return [
        GapRecord(
            gap_id=g.gap_id,
            gap_type=g.gap_type.value,
            description=g.missing,
            resolved=g.resolved,
            finding_id=g.finding_id,
        )
        for g in gaps
    ]


# --- the report -----------------------------------------------------------------


@router.get("/{run_id}/report", response_model=FinalReport)
async def get_report(run_id: str) -> FinalReport:
    return _report(run_id)


@router.get("/{run_id}/report.md", response_class=PlainTextResponse)
async def get_report_markdown(run_id: str) -> str:
    """The same report a human reads, as Markdown."""
    return to_markdown(_report(run_id))


# --- stopping -------------------------------------------------------------------


@router.post(
    "/{run_id}/cancel",
    response_model=CancelResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
async def cancel_mission(run_id: str) -> CancelResponse:
    """Ask a mission to stop. 202: cancellation is cooperative, so it is requested, not done.

    The run stops at its next await point - a tool call or model call boundary - and keeps
    whatever it had already established.
    """
    record = _require(run_id)
    cancelling = await get_registry().cancel(record)
    return CancelResponse(run_id=run_id, cancelling=cancelling, status=record.status)


# --- live -----------------------------------------------------------------------


@router.get("/{run_id}/stream")
async def stream(run_id: str, request: Request) -> Response:
    """Server-sent events for a running mission. See ADR-008."""
    record = _require(run_id)
    return stream_mission(record, request)


# --- shaping --------------------------------------------------------------------


def _require(run_id: str) -> MissionRecord:
    record = get_registry().get(run_id)
    if record is None:
        raise MissionNotFoundError(run_id)
    return record


def _report(run_id: str) -> FinalReport:
    record = _require(run_id)
    report = record.result.report if record.result else None
    if report is None:
        raise MissionNotFinishedError(run_id, "report", record.stage.value)
    return report


def _objective(body: CreateMissionRequest) -> Objective:
    attached = [
        AttachedDocument(
            document_id=name,
            name=name,
            kind=_KIND_BY_SUFFIX.get(name.rsplit(".", 1)[-1].lower(), DocumentKind.UNKNOWN),
        )
        for name in body.documents
    ]
    return Objective(text=body.objective, scope=ObjectiveScope(documents=attached))


def _summary(record: MissionRecord) -> MissionSummary:
    result = record.result
    return MissionSummary(
        run_id=record.run_id,
        objective=record.objective.text,
        status=record.status,
        stage=record.stage,
        documents=list(record.documents),
        created_at=record.created_at,
        finished_at=record.finished_at,
        finding_count=len(result.findings) if result else 0,
        verified_count=len(result.verified_findings) if result else 0,
        unresolved_gap_count=len(result.unresolved_gaps) if result else 0,
    )


def _detail(record: MissionRecord) -> MissionDetail:
    result = record.result
    intent = result.intent if result else None
    plan = result.plan if result else None
    base = _summary(record)
    return MissionDetail(
        **base.model_dump(),
        goal=intent.goal if intent else "",
        required_operations=(
            [op.operation.value for op in intent.required_operations] if intent else []
        ),
        task_count=len(plan.tasks) if plan else 0,
        replan_iterations=result.replan_iterations if result else 0,
        termination_reason=(
            result.termination_reason.value if result and result.termination_reason else ""
        ),
        error_code=result.error_code if result else "",
        error_message=result.error_message if result else "",
        clarification_question=(
            intent.clarification_question or ""
            if intent and record.status is MissionStatus.CLARIFICATION_NEEDED
            else ""
        ),
        has_report=bool(result and result.report),
    )


def snapshot_payloads(record: MissionRecord) -> dict[str, object]:
    """The run's final state in the exact shapes these routes serve.

    Used by `app/api/recording.py` so a replay is fed byte-identical payloads to a live view.
    Built from the same shapers the routes use rather than assembled separately: if the two
    ever diverged, a replay would stop being a faithful rendering of the run and become a
    second implementation of one.
    """
    result = record.result
    payload: dict[str, object] = {"mission": _detail(record).model_dump(mode="json")}

    if result is None:
        return payload

    if result.plan is not None:
        nodes = [
            TaskNode(
                task_id=task.task_id,
                task_type=task.task_type,
                description=task.description,
                status=task.status,
                depends_on=list(task.depends_on),
                tool_id=task.selection.tool_name if task.selection else "",
                inserted_by_replan=task.created_by_revision > 0,
            )
            for task in result.plan.tasks
        ]
        payload["tasks"] = TaskGraphResponse(
            run_id=record.run_id,
            nodes=nodes,
            edges=[(dep, t.task_id) for t in result.plan.tasks for dep in t.depends_on],
            waves=execution_levels(result.plan),
        ).model_dump(mode="json")

    payload["findings"] = FindingsResponse(
        run_id=record.run_id, findings=result.findings
    ).model_dump(mode="json")

    payload["gaps"] = [
        GapRecord(
            gap_id=g.gap_id,
            gap_type=g.gap_type.value,
            description=g.missing,
            resolved=g.resolved,
            finding_id=g.finding_id,
        ).model_dump(mode="json")
        for g in result.gaps
    ]

    if result.report is not None:
        payload["report"] = result.report.model_dump(mode="json")

    return payload


_KIND_BY_SUFFIX = {
    "pdf": DocumentKind.PDF,
    "csv": DocumentKind.CSV,
    "txt": DocumentKind.TEXT,
    "md": DocumentKind.MARKDOWN,
    "json": DocumentKind.JSON,
}
