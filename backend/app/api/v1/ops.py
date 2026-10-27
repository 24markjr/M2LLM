"""Operating JARVIS (v4 Phase 8): metrics and data governance, for the organisation's admins.

    GET  /ops/metrics?days=7                     investigations, latency, errors, tokens, cost
    GET  /ops/metrics/runs?days=7                the same, per investigation
    GET  /governance/policy                      retention and masking
    PUT  /governance/policy
    POST /governance/retention?dry_run=true      apply retention (or show what it would delete)
    POST /governance/subject/search              where a person's identifier appears (DPDP)
    POST /governance/subject/erase               erase it (confirm: "erase")
    GET  /governance/audit.csv                   the audit log as CSV
    GET  /packs                                  the domain packs, and the organisation's (anyone)
    GET|PUT /cases/{case_id}/watch               a case's watch folder and re-investigation schedule
    POST /cases/{case_id}/watch/scan             look in the folder now

Everything is the caller's organisation's (Phase 1c). Admin only, except /packs.
"""

from __future__ import annotations

from fastapi import APIRouter, Header, Query, status
from fastapi.responses import Response
from pydantic import Field

from app.api.errors import ApiError
from app.api.registry import get_registry
from app.llm import get_provider
from app.ops import governance, watch
from app.ops.metrics import RunMetrics, Summary, run_metrics, summarise
from app.packs import Pack, all_packs, current_pack
from app.review.service import audit
from app.schemas.common import JarvisModel

router = APIRouter(tags=["operations"])


class OpsSummary(Summary):
    model: str = ""
    model_healthy: bool = False


@router.get("/ops/metrics", response_model=OpsSummary)
async def metrics(days: int = Query(default=7, ge=1, le=365)) -> OpsSummary:
    registry = get_registry()
    summary = summarise(
        registry.records(), days=days, running=registry.running, waiting=registry.waiting
    )
    provider = get_provider()
    return OpsSummary(
        **summary.model_dump(), model=provider.model_id, model_healthy=await provider.health()
    )


@router.get("/ops/metrics/runs", response_model=list[RunMetrics])
async def run_list(days: int = Query(default=7, ge=1, le=365)) -> list[RunMetrics]:
    from datetime import timedelta

    from app.schemas.common import utcnow

    since = utcnow() - timedelta(days=days)
    return [run_metrics(r) for r in get_registry().records() if r.created_at >= since]


@router.get("/governance/policy", response_model=governance.Policy)
async def get_policy() -> governance.Policy:
    return governance.policy()


@router.put("/governance/policy", response_model=governance.Policy)
async def put_policy(
    body: governance.Policy,
    actor: str = Header(default="console", alias="X-Jarvis-User", max_length=128),
) -> governance.Policy:
    if body.pack not in {p.id for p in all_packs()}:
        raise ApiError(
            "UNKNOWN_PACK",
            f"no domain pack {body.pack!r}",
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
        )
    saved = governance.save_policy(body)
    await audit("governance.policy", actor=actor, target="policy", **body.model_dump())
    return saved


@router.post("/governance/retention", response_model=governance.RetentionResult)
async def retention(
    dry_run: bool = Query(default=True),
    actor: str = Header(default="console", alias="X-Jarvis-User", max_length=128),
) -> governance.RetentionResult:
    return await governance.apply_retention(dry_run=dry_run, actor=actor)


class SubjectRequest(JarvisModel):
    identifier: str = Field(min_length=3, max_length=200)
    confirm: str = ""


@router.post("/governance/subject/search", response_model=governance.SubjectReport)
async def subject_search(body: SubjectRequest) -> governance.SubjectReport:
    return await governance.find_subject(body.identifier)


@router.post("/governance/subject/erase", response_model=governance.SubjectReport)
async def subject_erase(
    body: SubjectRequest,
    actor: str = Header(default="console", alias="X-Jarvis-User", max_length=128),
) -> governance.SubjectReport:
    if body.confirm != "erase":
        raise ApiError(
            "CONFIRMATION_REQUIRED",
            'erasing needs confirm: "erase" - search first to see what would go',
            status_code=status.HTTP_400_BAD_REQUEST,
        )
    return await governance.erase_subject(body.identifier, actor=actor)


@router.get("/governance/audit.csv")
async def audit_export() -> Response:
    return Response(
        content=await governance.audit_csv(),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": 'attachment; filename="audit-log.csv"'},
    )


# --- domain packs (v4 Phase 10) ------------------------------------------------------------------
# Readable by everyone signed in: the console offers the pack's starter questions.


class Packs(JarvisModel):
    current: str
    packs: list[Pack] = Field(default_factory=list)


@router.get("/packs", response_model=Packs)
async def packs() -> Packs:
    return Packs(current=current_pack().id, packs=all_packs())


# --- watch folders (v4 Phase 10) -----------------------------------------------------------------


class WatchView(watch.WatchSettings):
    folder: str = ""


class WatchUpdate(JarvisModel):
    enabled: bool = False
    rerun_on_new_files: bool = True
    rerun_every_days: int = Field(default=0, ge=0, le=365)


@router.get("/cases/{case_id}/watch", response_model=WatchView)
async def get_watch(case_id: str) -> WatchView:
    return WatchView(**watch.load(case_id).model_dump(), folder=str(watch.folder(case_id)))


@router.put("/cases/{case_id}/watch", response_model=WatchView)
async def put_watch(case_id: str, body: WatchUpdate) -> WatchView:
    saved = watch.save(case_id, watch.load(case_id).model_copy(update=body.model_dump()))
    return WatchView(**saved.model_dump(), folder=str(watch.folder(case_id)))


@router.post("/cases/{case_id}/watch/scan", response_model=watch.ScanResult)
async def scan_now(
    case_id: str, actor: str = Header(default="console", alias="X-Jarvis-User", max_length=128)
) -> watch.ScanResult:
    """Look in the folder now instead of waiting for the next sweep."""
    return await watch.scan(case_id, actor=actor)
