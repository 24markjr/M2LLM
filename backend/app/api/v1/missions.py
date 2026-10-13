"""Mission routes.

Every handler reads from the registry and shapes a response. None of them runs the pipeline:
a mission is started as a background task and the request returns a run id immediately,
because an investigation takes a minute or more and a request that waits for one times out.

Nothing here blocks on the agent, and nothing here reaches into a model. Invariant 1 holds
at this layer for free - the API has no LLM dependency at all, only the orchestrator does.
"""

from __future__ import annotations

from fastapi import APIRouter, Header, Query, Request, Response, status
from fastapi.responses import PlainTextResponse

from app.api.archive import write_archive
from app.api.deletion import DeletionReport, delete_all_investigations, delete_investigation
from app.api.errors import ApiError, MissionNotFinishedError, MissionNotFoundError
from app.api.registry import MissionRecord, case_investigation, get_registry
from app.api.v1.schemas import (
    CancelResponse,
    CreateMissionRequest,
    EventPage,
    EventRecord,
    FindingChain,
    FindingsResponse,
    GapRecord,
    MissionDetail,
    MissionSummary,
    PlanTree,
    TaskGraphResponse,
    TaskNode,
)
from app.api.v1.stream import stream_mission
from app.cases.service import file_evidence, file_investigation, get_case_store, start_investigating
from app.core.logging import get_logger
from app.evidence.authority import authority_map
from app.evidence.service import admit_for_mission, authority_of, record_analysed
from app.integrations.context import workspace_retriever
from app.integrations.verification import build_verification_provider
from app.intelligence.challenge import ChallengeResult, challenge
from app.intelligence.confidence import why
from app.intelligence.planner.engine import execution_levels
from app.intelligence.synthesis.renderers import to_markdown
from app.llm import get_provider
from app.orchestration.labels import step_label
from app.orchestration.mission import MissionStatus
from app.schemas.case import Case, CaseStatus
from app.schemas.hypothesis import HypothesisSet
from app.schemas.objective import AttachedDocument, DocumentKind, Objective, ObjectiveScope
from app.schemas.result import FinalReport
from app.tools.formats import prepare
from app.tools.loader import load_by_name, resolve_document

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

    # Images, scans, video and audio are understood before they are read (Phase 39): once per
    # file, cached, so a file uploaded earlier costs nothing here.
    case = await _require_case(body.case_id) if body.case_id else None
    paths = {name: resolve_document(name) for name in body.documents}
    # Every document is evidence (Phase 43): registered on first use, and checked against its hash
    # before the mission reads it. A file whose bytes changed is left out, and the mission says so.
    admitted, excluded = await admit_for_mission(paths)
    readable = [name for name in body.documents if name not in excluded]
    await prepare([paths[n] for n in readable], get_provider())
    documents, loaded = load_by_name(readable)
    missing = [name for name in readable if name not in documents]
    if body.documents and not documents:
        raise ApiError(
            "NO_READABLE_DOCUMENTS",
            "none of the attached documents could be read"
            + (" (failed integrity: " + "; ".join(excluded.values()) + ")" if excluded else ""),
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            details={"requested": body.documents, "excluded": excluded},
        )
    if missing:
        # The run proceeds on what was readable, and says what it excluded. Silently
        # investigating a subset would let a partial read pass for a full one.
        log.warning("documents_excluded", missing=missing)

    retriever = None
    if body.workspace_id and documents:
        # Ingested before the run starts (unchanged files are skipped by hash), so the mission's
        # first recall already searches them. A store or embedding failure leaves recall lexical.
        retriever = await workspace_retriever(body.workspace_id, documents, loaded, get_provider())

    # Each document's source authority (Phase 45): its evidence item's tier, else the intake rules.
    authority = authority_map(
        sorted(documents),
        await authority_of({n: admitted[n] for n in documents if n in admitted}),
    )
    record = await registry.create(
        objective=_objective(body),
        documents=sorted(documents),
        loaded=documents,
        page_starts={d.document_id: d.page_starts for d in loaded if d.page_starts},
        provider=get_provider(),
        retriever=retriever,
        authority=authority,
    )
    record.evidence = {name: admitted[name] for name in documents if name in admitted}
    record.excluded = excluded
    await record_analysed(record.run_id, record.evidence)
    if case is not None:
        # Filed in its case with its evidence (Phase 44). An open case is now being investigated.
        record.case_id = case.case_id
        await file_investigation(case_investigation(record))
        await file_evidence(case.case_id, list(admitted.values()))
        await start_investigating(case)
    return _detail(record)


@router.delete("/{run_id}", response_model=DeletionReport)
async def delete_mission(
    run_id: str,
    actor: str = Header(default="console", alias="X-Jarvis-User", max_length=128),
) -> DeletionReport:
    """Delete one finished investigation everywhere it is held (Phase U1): the run, its archive and
    recordings, the stored run, its memory support, its place in its case. The response says what
    went and what is kept: custody, review decisions and the audit log are append-only."""
    return await delete_investigation(run_id, actor=actor)


@router.delete("", response_model=DeletionReport)
async def delete_missions(
    confirm: str = Query(default=""),
    actor: str = Header(default="console", alias="X-Jarvis-User", max_length=128),
) -> DeletionReport:
    """Delete every finished investigation; `confirm=delete` required, running ones skipped."""
    if confirm != "delete":
        raise ApiError(
            "CONFIRMATION_REQUIRED",
            "deleting every investigation needs confirm=delete",
            status_code=status.HTTP_400_BAD_REQUEST,
        )
    return await delete_all_investigations(actor=actor)


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
            label=step_label(task.task_type, task.status),
            rationale=task.rationale,
            workstream=task.workstream,
        )
        for task in plan.tasks
    ]
    edges = [(dep, task.task_id) for task in plan.tasks for dep in task.depends_on]
    return TaskGraphResponse(run_id=run_id, nodes=nodes, edges=edges, waves=execution_levels(plan))


@router.get("/{run_id}/plan", response_model=PlanTree)
async def get_plan_tree(run_id: str) -> PlanTree:
    """The plan as a person reads it (Phase 49): objective, workstreams, and each step's why,
    inputs, action, output, dependencies and status; then every change the run made, and why."""
    record = _require(run_id)
    result = record.result
    if result is None or result.plan is None:
        raise MissionNotFinishedError(run_id, "plan", record.stage.value)
    from app.api.plan_tree import plan_tree  # imports these schemas; imported late

    return plan_tree(run_id, result)


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
    return FindingsResponse(
        run_id=run_id, findings=findings, why={f.finding_id: why(f) for f in findings}
    )


@router.post("/{run_id}/findings/{finding_id}/challenge", response_model=ChallengeResult)
async def challenge_finding(
    run_id: str,
    finding_id: str,
    actor: str = Header(default="console", alias="X-Jarvis-User", max_length=128),
) -> ChallengeResult:
    """Challenge one finding (Phase 48): look for counter-evidence in the run's documents, check
    its own lines, verify it against the counter lines with the configured verifier, weigh
    authority, and recompute its confidence. The finding itself is not changed; the challenge is
    kept beside it, with who asked."""
    record = _require(run_id)
    result = record.result
    finding = next(
        (f for f in (result.findings if result else []) if f.finding_id == finding_id), None
    )
    if result is None or finding is None:
        raise ApiError(
            "FINDING_NOT_FOUND",
            f"no finding {finding_id} in {run_id}",
            status_code=status.HTTP_404_NOT_FOUND,
        )
    verifier = build_verification_provider(get_provider())
    outcome = await challenge(
        finding,
        record.texts,
        page_starts=record.page_starts,
        authority=record.authority,
        evidence_text=result.evidence_text,
        verifier=verifier.verify,
        actor=actor,
    )
    record.challenges[finding_id] = outcome
    write_archive(record)  # a challenge is part of the run's record (Phase U1)
    return outcome


@router.get("/{run_id}/challenges", response_model=list[ChallengeResult])
async def get_challenges(run_id: str) -> list[ChallengeResult]:
    """Every challenge made of this run's findings, latest per finding (Phase 48)."""
    return list(_require(run_id).challenges.values())


@router.get("/{run_id}/hypotheses", response_model=HypothesisSet)
async def get_hypotheses(run_id: str) -> HypothesisSet:
    """The competing explanations, ranked by computed support, with what would decide each and
    where to look next (Phase 47). Empty with a reason when the objective asked for none."""
    record = _require(run_id)
    result = record.result
    if result is None or result.hypotheses is None:
        return HypothesisSet(skipped_reason="the run has not reached this step")
    return result.hypotheses


@router.get("/{run_id}/findings/{finding_id}/chain", response_model=FindingChain)
async def get_finding_chain(run_id: str, finding_id: str) -> FindingChain:
    """From claim to conclusion (Phase 46): each citation with its evidence item, authority, line
    text and what was extracted from it; how reasoning proposed it; what each verifier said; and
    the confidence with its factors."""
    record = _require(run_id)
    result = record.result
    finding = next(
        (f for f in (result.findings if result else []) if f.finding_id == finding_id), None
    )
    if result is None or finding is None:
        raise ApiError(
            "FINDING_NOT_FOUND",
            f"no finding {finding_id} in {run_id}",
            status_code=status.HTTP_404_NOT_FOUND,
        )
    from app.api.chain import finding_chain  # chain imports these schemas; imported late

    return finding_chain(run_id, finding, result, record.evidence, record.authority, record.events)


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


async def _require_case(case_id: str) -> Case:
    try:
        store = await get_case_store()
        case = await store.get(case_id)
    except Exception as exc:
        raise ApiError(
            "CASES_UNAVAILABLE",
            f"the case store could not be read: {type(exc).__name__}",
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        ) from exc
    if case is None:
        raise ApiError(
            "CASE_NOT_FOUND", f"no case {case_id}", status_code=status.HTTP_404_NOT_FOUND
        )
    if case.status is CaseStatus.CLOSED:
        raise ApiError(
            "CASE_CLOSED",
            f"{case_id} is closed; reopen it to investigate further",
            status_code=status.HTTP_409_CONFLICT,
        )
    return case


def _objective(body: CreateMissionRequest) -> Objective:
    attached = [
        AttachedDocument(
            document_id=name,
            name=name,
            kind=_KIND_BY_SUFFIX.get(name.rsplit(".", 1)[-1].lower(), DocumentKind.UNKNOWN),
        )
        for name in body.documents
    ]
    return Objective(text=body.objective, scope=ObjectiveScope(documents=attached), mode=body.mode)


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
        case_id=record.case_id,
        mode=record.objective.mode,
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
        security_flags=list(result.security) if result else [],
        knowledge_store=result.knowledge_store if result else "",
        knowledge_entities=len(result.knowledge.entities) if result and result.knowledge else 0,
        knowledge_claims=len(result.knowledge.claims) if result and result.knowledge else 0,
        knowledge_conflicts=(len(result.knowledge.conflicts) if result and result.knowledge else 0),
        evidence=dict(record.evidence),
        excluded_documents=dict(record.excluded),
        authority=dict(record.authority),
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

    # The knowledge graph, so a replay opens the 3D explorer from the recording alone.
    if result.knowledge is not None and record.knowledge_view is not None:
        payload["knowledge"] = {
            "snapshot": result.knowledge.model_dump(mode="json"),
            "timeline": record.knowledge_timeline or [],
            "graph": record.knowledge_view,
        }

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
                label=step_label(task.task_type, task.status),
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
        run_id=record.run_id,
        findings=result.findings,
        why={f.finding_id: why(f) for f in result.findings},
    ).model_dump(mode="json")

    if result.hypotheses is not None:
        payload["hypotheses"] = result.hypotheses.model_dump(mode="json")

    if result.plan is not None:
        from app.api.plan_tree import plan_tree  # imports these schemas; imported late

        payload["plan"] = plan_tree(record.run_id, result).model_dump(mode="json")

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
