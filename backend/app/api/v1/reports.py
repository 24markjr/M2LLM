"""The investigation report over HTTP (Phase 51): the object, and its exports.

`GET .../investigation-report` returns the report as JSON and changes nothing. An export - Markdown,
PDF, DOCX or JSON - is an act with consequences for the evidence: each document the report cites
gets a REPORTED event in its chain of custody, and the export is in the audit log with the report's
content hash, so a copy found later can be matched to the one the system produced.
"""

from __future__ import annotations

from fastapi import APIRouter, Header, Query, status
from fastapi.responses import Response

from app.api.archive import write_archive
from app.api.errors import ApiError
from app.api.registry import MissionRecord, get_registry
from app.core.config import get_settings
from app.core.logging import get_logger
from app.evidence import service as evidence_service
from app.intelligence.challenge import challenge
from app.language import LANGUAGES, TranslationUnavailable
from app.language.routing import strictest
from app.ops import governance
from app.packs import current_pack
from app.reporting import versions as report_versions
from app.reporting.builder import (
    build_report,
    get_report_settings,
    get_severity_rules,
    severity_of,
)
from app.reporting.document import build_document
from app.reporting.export import to_markdown
from app.reporting.render import render_docx, render_html, render_pdf
from app.reporting.translate import translated
from app.reporting.units import unit_mismatch
from app.review.service import audit, get_review_store, requirements, review_of
from app.schemas.evidence_locker import CustodyAction, EvidenceClassification, EvidenceItem
from app.schemas.investigation_report import InvestigationReport

log = get_logger(__name__)
router = APIRouter(tags=["reports"])

FORMATS = {
    "md": ("text/markdown; charset=utf-8", "md"),
    "pdf": ("application/pdf", "pdf"),
    "docx": (
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        "docx",
    ),
    "json": ("application/json", "json"),
    # v4 Phase 5: the designed report as one self-contained page, for the screen and for printing.
    "html": ("text/html; charset=utf-8", "html"),
}


def _record(run_id: str) -> MissionRecord:
    record = get_registry().get(run_id)
    if record is None:
        raise ApiError(
            "MISSION_NOT_FOUND", f"no mission {run_id}", status_code=status.HTTP_404_NOT_FOUND
        )
    if record.result is None or not record.is_finished():
        raise ApiError(
            "MISSION_NOT_FINISHED",
            f"{run_id} has not finished; its report is not settled",
            status_code=status.HTTP_409_CONFLICT,
        )
    return record


async def assemble(record: MissionRecord) -> InvestigationReport:
    from app.api.registry import _case_severity, attack_locators, cites
    from app.api.v1.missions import _receipt

    result = record.result
    assert result is not None
    severity = await _case_severity(record.case_id)
    await _challenge_severe(record, severity)
    decisions = await (await get_review_store()).decisions(record.run_id)
    reviews = {}
    for finding in result.findings:
        challenge = record.challenges.get(finding.finding_id)
        reasons = requirements(
            finding,
            case_severity=severity,
            challenge_outcome=challenge.outcome.value if challenge else "",
            attack_mapped=cites(finding, attack_locators(record)),
        )
        reviews[finding.finding_id] = review_of(record.run_id, finding, decisions, reasons)
    items: dict[str, EvidenceItem] = {}
    try:
        locker = await evidence_service.get_locker()
        for name, evidence_id in record.evidence.items():
            item = await locker.get(evidence_id)
            if item is not None:
                items[name] = item
    except Exception:  # noqa: BLE001 - a report without hashes still reports; it says so per item
        items = {}
    return build_report(
        result,
        case_id=record.case_id,
        case_severity=severity,
        items=items,
        authority=record.authority,
        reviews=reviews,
        challenges=record.challenges,
        events=list(record.events),
        model=get_settings().ollama_model,
        receipt_hash=_receipt(record).receipt_hash,
        pack=current_pack(),
    )


async def _challenge_severe(record: MissionRecord, case_severity: str) -> None:
    """Challenge every HIGH or CRITICAL finding nobody has challenged yet, before it is reported
    (Phase 48's deferred step, now that severity exists). The deterministic rule only: a report must
    not wait on a model, and the challenge is kept on the run like one a person asked for."""
    result = record.result
    assert result is not None
    rules = get_severity_rules()
    severe = set(get_report_settings().challenge_before_report)
    for finding in result.findings:
        if finding.finding_id in record.challenges:
            continue
        cited = [
            result.evidence_text.get(r.as_ref(), "") for r in finding.evidence if r.is_resolved
        ]
        level, _ = severity_of(
            finding,
            unit_issue=unit_mismatch(finding.claim, cited),
            challenge=None,
            case_severity=case_severity,
            rules=rules,
        )
        if level not in severe:
            continue
        record.challenges[finding.finding_id] = await challenge(
            finding,
            record.texts,
            page_starts=record.page_starts,
            authority=record.authority,
            evidence_text=result.evidence_text,
            actor="system (before the report)",
        )
        await audit(
            "challenge.before_report",
            target=f"{record.run_id}/{finding.finding_id}",
            severity=level.value,
            outcome=record.challenges[finding.finding_id].outcome.value,
        )
        write_archive(record)  # Phase U1: the challenge is part of the run's record


@router.get("/missions/{run_id}/investigation-report", response_model=InvestigationReport)
async def get_investigation_report(run_id: str) -> InvestigationReport:
    """The report as it stands now: findings with their reviews and challenges, evidence with hashes
    and integrity, timeline, contradictions, explanations, unknowns, recommendations, trace."""
    return await assemble(_record(run_id))


@router.get("/missions/{run_id}/investigation-report/export/{fmt}")
async def export_investigation_report(
    run_id: str,
    fmt: str,
    actor: str = Header(default="console", alias="X-Jarvis-User", max_length=128),
    language: str = Query(default="", pattern=r"^[a-z]{0,3}$"),
) -> Response:
    """Download the report as md, pdf, docx or json. Recorded: a REPORTED custody event on every
    cited evidence item, and an audit entry carrying the content hash. `language` (v4 Phase 7):
    html or docx in an Indian language, a labelled translation of the verified English."""
    if fmt not in FORMATS:
        raise ApiError(
            "UNSUPPORTED_FORMAT",
            f"export as one of {', '.join(FORMATS)}",
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
        )
    target = LANGUAGES.get(language) if language and language != "en" else None
    if language and language != "en" and target is None:
        raise ApiError(
            "UNSUPPORTED_LANGUAGE",
            f"no language {language!r}; one of {', '.join(sorted(LANGUAGES))}",
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
        )
    if target is not None and fmt not in ("html", "docx"):
        raise ApiError(
            "ENGLISH_ONLY_FORMAT",
            f"{fmt} is English only; a report in {target.name} is html or docx",
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
        )
    record = _record(run_id)
    report = await assemble(record)
    # The designed document (v4 Phase 5): HTML, PDF and DOCX draw the same blocks.
    document = build_document(report, current_pack().report)
    if governance.policy().mask_personal_data:  # v4 Phase 8: what leaves is masked
        document = governance.mask_document(document)
    if target is not None:
        try:
            document = await translated(document, target, await _sensitivity(record))
        except TranslationUnavailable as exc:
            raise ApiError(
                "TRANSLATION_UNAVAILABLE",
                f"the report cannot be translated here: {exc}",
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            ) from exc
    if fmt == "pdf":
        body: bytes = render_pdf(document)
    elif fmt == "docx":
        body = render_docx(document)
    elif fmt == "html":
        body = render_html(document).encode("utf-8")
    elif fmt == "json":
        body = report.model_dump_json(indent=2).encode("utf-8")
    else:
        body = to_markdown(report).encode("utf-8")

    cited = [e for e in report.evidence if e.evidence_id and e.cited_by]
    try:
        locker = await evidence_service.get_locker()
        for item in cited:
            await evidence_service.note(
                locker,
                item.evidence_id,
                CustodyAction.REPORTED,
                actor=actor,
                report_id=report.report_id,
                content_hash=report.content_hash,
                format=fmt,
                findings=item.cited_by,
            )
    except Exception as exc:  # noqa: BLE001 - custody never fails the export it records
        log.warning("report_custody_not_recorded", run_id=run_id, error=str(exc))
    await audit(
        "report.exported",
        actor=actor,
        target=run_id,
        format=fmt,
        report_id=report.report_id,
        content_hash=report.content_hash,
        evidence=[e.evidence_id for e in cited],
    )
    version = report_versions.record(report, f"{fmt}:{target.code}" if target else fmt, actor)
    media, extension = FORMATS[fmt]
    # HTML opens in the browser; the files download.
    disposition = "inline" if fmt == "html" else "attachment"
    return Response(
        content=body,
        media_type=media,
        headers={
            "Content-Disposition": f'{disposition}; filename="{report.report_id}-v{version.version}'
            f'.{extension}"',
            "X-Report-Hash": report.content_hash,
            "X-Report-Version": str(version.version),
            "X-Receipt-Hash": report.receipt_hash,
        },
    )


async def _sensitivity(record: MissionRecord) -> EvidenceClassification | None:
    """The run is as sensitive as its most sensitive file (v4 Phase 7): what may translate it."""
    levels: list[EvidenceClassification | None] = []
    try:
        locker = await evidence_service.get_locker()
        for evidence_id in record.evidence.values():
            item = await locker.get(evidence_id)
            levels.append(item.classification if item is not None else None)
    except Exception:  # noqa: BLE001 - unknown is the strictest
        return None
    return strictest(levels)


@router.get(
    "/missions/{run_id}/investigation-report/versions",
    response_model=list[report_versions.ReportVersion],
)
async def get_report_versions(run_id: str) -> list[report_versions.ReportVersion]:
    """Every export of this run's report: number, format, who, and the content, receipt and case
    snapshot hashes it was signed with (v4 Phase 5)."""
    _record(run_id)
    return report_versions.versions(run_id)
