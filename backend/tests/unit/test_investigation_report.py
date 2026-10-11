"""Phase 51: the investigation report - one object, three exports, every export on the record.

The executive summary and the risk come only from findings that count; severity is set by declared
rules; the currency check catches a claim whose unit is not its evidence's; the PDF, DOCX and
Markdown are drawn from the same sections and each carries the content hash; and exporting writes a
REPORTED event into the custody of every cited document and an entry into the audit log.
"""

from __future__ import annotations

import io

import pytest
from docx import Document
from httpx import ASGITransport, AsyncClient
from pypdf import PdfReader

from app.api.app import create_app
from app.api.registry import MissionRecord, get_registry
from app.evidence import service as evidence_service
from app.orchestration.mission import MissionResult, MissionStatus, Stage
from app.reporting.builder import build_report, content_hash, get_severity_rules, severity_of
from app.reporting.export import to_docx, to_markdown, to_pdf
from app.reporting.units import currencies, unit_mismatch
from app.review.service import get_review_store
from app.schemas.common import SourceLocator, new_run_id
from app.schemas.event import EventType, ExecutionEvent
from app.schemas.evidence import EvidenceRef, ResolutionStatus
from app.schemas.evidence_locker import EvidenceItem
from app.schemas.finding import Finding, StatementType
from app.schemas.investigation_report import Severity
from app.schemas.objective import AttachedDocument, Objective, ObjectiveScope
from app.schemas.review import FindingReview, ReviewDecision, ReviewState
from app.schemas.verification import VerificationResult, VerificationStatus


def _finding(
    finding_id: str,
    claim: str,
    cite: str,
    *,
    statement: StatementType = StatementType.SOURCE_CLAIM,
    verified: bool = True,
) -> Finding:
    document, row = cite.rsplit(":r", 1)
    return Finding(
        finding_id=finding_id,
        claim=claim,
        evidence=[
            EvidenceRef(
                evidence_id="E-001",
                locator=SourceLocator(document_id=document, document_name=document, row=int(row)),
                resolution=ResolutionStatus.RESOLVED,
            )
        ],
        statement_type=statement,
        statement_basis=StatementType.SOURCE_CLAIM,
        verification=VerificationResult(status=VerificationStatus.SUPPORTED, confidence=0.9)
        if verified
        else None,
    )


TEXT = {
    "ledger.txt:r3": "Spend to date: INR 287,500 against the approved INR 250,000.",
    "plan.txt:r2": "The go-live date is 12 June 2026.",
}


# --- the currency check ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("text", "found"),
    [
        ("$287,500", {"USD"}),
        ("INR 287,500", {"INR"}),
        ("Rs. 2.5 lakh", {"INR"}),
        ("₹ 40,000", {"INR"}),
        ("EUR 10,000 and £5", {"EUR", "GBP"}),
        ("287,500", set()),
    ],
)
def test_currencies_are_read_from_symbols_codes_and_words(text: str, found: set[str]) -> None:
    assert currencies(text) == found


def test_a_dollar_claim_over_rupee_evidence_is_a_unit_mismatch() -> None:
    assert unit_mismatch("Spend reached $287,500.", [TEXT["ledger.txt:r3"]]) == (
        "the claim states USD where its cited lines state INR"
    )
    assert unit_mismatch("Spend reached INR 287,500.", [TEXT["ledger.txt:r3"]]) == ""
    assert unit_mismatch("Spend reached 287,500.", [TEXT["ledger.txt:r3"]]) == ""


# --- severity -------------------------------------------------------------------------------------


def test_severity_is_the_highest_rule_and_says_which() -> None:
    rules = get_severity_rules()
    plain = _finding("F-001", "x", "plan.txt:r2")
    assert severity_of(plain, unit_issue="", challenge=None, case_severity="", rules=rules) == (
        Severity.LOW,
        "no rule raised it",
    )
    contradiction = _finding("F-002", "x", "plan.txt:r2", statement=StatementType.CONTRADICTION)
    assert severity_of(
        contradiction, unit_issue="", challenge=None, case_severity="", rules=rules
    ) == (Severity.HIGH, "it reports a contradiction")
    assert severity_of(plain, unit_issue="", challenge=None, case_severity="HIGH", rules=rules) == (
        Severity.MEDIUM,
        "its case is HIGH",
    )
    assert (
        severity_of(plain, unit_issue="USD vs INR", challenge=None, case_severity="", rules=rules)[
            0
        ]
        is Severity.HIGH
    )


# --- the report -----------------------------------------------------------------------------------


def _result() -> MissionResult:
    return MissionResult(
        run_id=new_run_id(),
        objective=Objective(
            text="Did Orion overspend?",
            scope=ObjectiveScope(
                documents=[
                    AttachedDocument(document_id="ledger.txt", name="ledger.txt"),
                    AttachedDocument(document_id="plan.txt", name="plan.txt"),
                ]
            ),
        ),
        findings=[
            _finding("F-001", "The go-live date is 12 June 2026.", "plan.txt:r2"),
            _finding(
                "F-002",
                "Spend of INR 287,500 exceeds the approved INR 250,000.",
                "ledger.txt:r3",
                statement=StatementType.CONTRADICTION,
            ),
            _finding("F-003", "Spend reached $287,500.", "ledger.txt:r3"),
            _finding("F-004", "The vendor was paid twice.", "ledger.txt:r3", verified=False),
        ],
        evidence_text=TEXT,
    )


def _pending(finding_id: str) -> FindingReview:
    return FindingReview(
        run_id="r",
        finding_id=finding_id,
        claim="",
        required=True,
        required_because=["it reports a contradiction"],
    )


def test_only_findings_that_count_reach_the_summary_and_the_risk() -> None:
    report = build_report(_result(), reviews={"F-002": _pending("F-002")})

    assert [f.finding_id for f in report.established] == ["F-001"]
    assert [f.finding_id for f in report.awaiting_review] == ["F-002"]
    assert {f.finding_id for f in report.not_established} == {"F-003", "F-004"}
    assert report.executive_summary == ["The go-live date is 12 June 2026. [F-001; plan.txt:r2]"]
    assert report.risk is Severity.LOW, "the HIGH contradiction awaits review and cannot raise it"
    unit = next(f for f in report.not_established if f.finding_id == "F-003")
    assert unit.unit_issues == ["the claim states USD where its cited lines state INR"]
    assert unit.severity is Severity.HIGH


def test_approval_moves_a_finding_into_the_summary_and_the_risk() -> None:
    approved = _pending("F-002").model_copy(
        update={
            "state": ReviewState.APPROVED,
            "history": [
                ReviewDecision(
                    run_id="r", finding_id="F-002", state=ReviewState.APPROVED, reviewer="lead"
                )
            ],
        }
    )
    report = build_report(_result(), reviews={"F-002": approved})
    assert {f.finding_id for f in report.established} == {"F-001", "F-002"}
    assert report.risk is Severity.HIGH and report.risk_reason.startswith("F-002")


def test_the_hash_covers_the_content() -> None:
    report = build_report(_result())
    assert report.content_hash == content_hash(report)
    changed = report.model_copy(update={"objective": "Something else?"})
    assert content_hash(changed) != report.content_hash
    rebuilt = build_report(report_result := _result())
    assert build_report(report_result).content_hash == rebuilt.content_hash, "time is not content"


def test_the_timeline_and_recommendations_come_from_the_run() -> None:
    report = build_report(_result(), reviews={"F-002": _pending("F-002")})
    assert report.timeline[0].date == "2026-06-12"
    assert "Decide on F-002" in report.recommendations[0]
    assert any("Establish which source is current for F-002" in r for r in report.recommendations)


# --- the exports ----------------------------------------------------------------------------------


def test_every_export_carries_the_same_sections_and_the_hash() -> None:
    report = build_report(
        _result(),
        events=[
            ExecutionEvent(run_id=_result().run_id, event_type=EventType.RUN_STARTED, t_offset_ms=0)
        ]
        * 120,
    )
    markdown = to_markdown(report)
    assert "## Executive summary" in markdown and report.content_hash in markdown

    pdf = PdfReader(io.BytesIO(to_pdf(report)))
    text = "\n".join(page.extract_text() for page in pdf.pages)
    assert len(pdf.pages) >= 2, "a long trace runs over pages"
    assert "Investigation Report" in text and "Executive summary" in text
    assert "12 June 2026" in text
    assert report.content_hash[:23] in text

    document = Document(io.BytesIO(to_docx(report)))
    headings = [p.text for p in document.paragraphs if p.style.name.startswith("Heading")]
    assert "Executive summary" in headings and "Trace" in headings
    assert any(report.content_hash in p.text for p in document.paragraphs)


def test_characters_a_pdf_font_lacks_are_written_readably() -> None:
    report = build_report(_result())
    report.objective = "Spend → ₹ 40,000 — “approved”"
    text = PdfReader(io.BytesIO(to_pdf(report))).pages[0].extract_text()
    assert 'Spend -> INR  40,000 - "approved"' in text


# --- the API --------------------------------------------------------------------------------------


async def test_an_export_is_written_to_custody_and_the_audit_log() -> None:
    result = _result()
    record = MissionRecord(result.run_id, result.objective, ["ledger.txt", "plan.txt"])
    record.status = MissionStatus.COMPLETED
    record.stage = Stage.DONE
    record.result = result
    locker = await evidence_service.get_locker()
    item = await locker.add(EvidenceItem(evidence_id="EV-000901", sha256="a" * 64, name="plan.txt"))
    record.evidence = {"plan.txt": item.evidence_id}
    get_registry()._missions[record.run_id] = record

    async with AsyncClient(transport=ASGITransport(app=create_app()), base_url="http://test") as c:
        report = (await c.get(f"/api/v1/missions/{record.run_id}/investigation-report")).json()
        pdf = await c.get(
            f"/api/v1/missions/{record.run_id}/investigation-report/export/pdf",
            headers={"X-Jarvis-User": "lead-1"},
        )
        bad = await c.get(f"/api/v1/missions/{record.run_id}/investigation-report/export/xls")

    assert report["evidence"][1]["evidence_id"] == "EV-000901"
    assert pdf.status_code == 200 and pdf.content.startswith(b"%PDF-1.4")
    assert pdf.headers["X-Report-Hash"] == report["content_hash"]
    assert bad.status_code == 422

    custody = [e for e in await locker.history("EV-000901") if e.action.value == "REPORTED"]
    assert custody and custody[0].actor == "lead-1"
    assert custody[0].details["content_hash"] == report["content_hash"]
    audit = await (await get_review_store()).audit(target=record.run_id)
    assert any(e.action == "report.exported" and e.details["format"] == "pdf" for e in audit)
    # The HIGH contradiction was challenged before it was reported (Phase 48's deferred step).
    assert any(e.action == "challenge.before_report" for e in audit)
    assert "F-002" in record.challenges and "F-001" not in record.challenges


async def test_an_unfinished_run_has_no_report() -> None:
    record = MissionRecord(new_run_id(), Objective(text="Still running?"), [])
    record.result = MissionResult(run_id=record.run_id, objective=record.objective)
    get_registry()._missions[record.run_id] = record
    async with AsyncClient(transport=ASGITransport(app=create_app()), base_url="http://test") as c:
        response = await c.get(f"/api/v1/missions/{record.run_id}/investigation-report")
    assert response.status_code == 409
