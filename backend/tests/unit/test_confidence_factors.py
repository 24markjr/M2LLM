"""Phase 46: confidence from named factors, "why?", and the evidence chain.

Measured before: 22 of 26 recorded findings sat at exactly 0.85, and a finding the verifier
rejected kept its 0.85. Now the value is resolution x (sum of weight x factor) - penalties, capped,
with every term kept - so the explanation's numbers add up, and verification moves the number.
"""

from __future__ import annotations

import pytest

from app.api.chain import finding_chain
from app.intelligence.confidence import assess, rescore, why
from app.intelligence.reasoning.statements import type_statements
from app.orchestration.mission import MissionResult
from app.schemas.common import new_run_id
from app.schemas.event import EventType, ExecutionEvent
from app.schemas.evidence import ClaimElement, EvidenceRef, ResolutionStatus, SourceLocator
from app.schemas.finding import Confidence, Finding, FindingClassification
from app.schemas.knowledge import KnowledgeClaim, KnowledgeEntity, KnowledgeSnapshot
from app.schemas.objective import Objective
from app.schemas.verification import (
    IssueType,
    VerificationIssue,
    VerificationResult,
    VerificationStatus,
    VerifierOpinion,
)


def _ref(document: str, row: int | None = None, page: int | None = None) -> EvidenceRef:
    return EvidenceRef(
        evidence_id=f"E-{(row or page or 0):03d}",
        locator=SourceLocator(document_id=document, document_name=document, row=row, page=page),
        resolution=ResolutionStatus.RESOLVED,
    )


def _finding(
    claim: str,
    *refs: EvidenceRef,
    status: VerificationStatus | None = VerificationStatus.SUPPORTED,
    finding_id: str = "F-001",
) -> Finding:
    finding = Finding(
        finding_id=finding_id,
        claim=claim,
        evidence=list(refs),
        elements=[ClaimElement(text=claim, supported=True)],
        verification=(
            VerificationResult(
                status=status,
                confidence=0.9,
                verifier="composite",
                issues=(
                    []
                    if status is VerificationStatus.SUPPORTED
                    else [
                        VerificationIssue(
                            issue_type=IssueType.EVIDENCE_MISMATCH, description="not on the line"
                        )
                    ]
                ),
            )
            if status
            else None
        ),
    )
    finding.classification = finding.classify()
    return finding


TEXT = {
    "sow.docx:r50": "Deliverables include a Bill of Material (BOM).",
    "report.txt:r10": "The completion date is 30 April 2026.",
    "finance.txt:r12": "Completion is forecast for 14 May 2026.",
}


def _terms_add_up(confidence: Confidence) -> None:
    weighted = [f for f in confidence.factors if f.weight > 0]
    assert sum(f.weight for f in weighted) == pytest.approx(1.0)
    assert sum(f.contribution for f in weighted) == pytest.approx(confidence.weighted)
    expected = confidence.resolution_rate * confidence.weighted - confidence.penalty
    assert confidence.value == pytest.approx(
        max(0.0, min(expected, confidence.classification_ceiling))
    )


def test_the_value_is_the_sum_of_its_terms() -> None:
    confidence = assess(_finding("The SoW lists a BOM.", _ref("sow.docx", 50)), evidence_text=TEXT)
    _terms_add_up(confidence)
    assert [f.name for f in confidence.factors] == [
        "resolution",
        "evidence_strength",
        "independence",
        "authority",
        "verification",
        "temporal_consistency",
    ]


def test_verification_moves_the_number() -> None:
    """The defect measured: a rejected finding kept 0.85."""
    supported = assess(_finding("The SoW lists a BOM.", _ref("sow.docx", 50)), evidence_text=TEXT)
    rejected = assess(
        _finding(
            "The SoW lists a BOM.", _ref("sow.docx", 50), status=VerificationStatus.UNSUPPORTED
        ),
        evidence_text=TEXT,
    )
    unverified = assess(
        _finding("The SoW lists a BOM.", _ref("sow.docx", 50), status=None), evidence_text=TEXT
    )
    assert supported.value > unverified.value > rejected.value


def test_a_second_document_raises_independence() -> None:
    one = assess(_finding("x", _ref("a.txt", 1), _ref("a.txt", 2)))
    two = assess(_finding("x", _ref("a.txt", 1), _ref("b.txt", 2)))
    independence = {c.name: c.value for c in two.factors}["independence"]
    assert {c.name: c.value for c in one.factors}["independence"] < independence
    assert two.weighted > one.weighted


def test_a_page_citation_is_weaker_than_a_line() -> None:
    line = assess(_finding("x", _ref("a.pdf", row=3)))
    page = assess(_finding("x", _ref("a.pdf", page=3)))
    strength = {c.name: c.value for c in page.factors}["evidence_strength"]
    assert strength == pytest.approx(0.7)
    assert line.weighted > page.weighted


def test_authority_is_one_weighted_factor() -> None:
    approved = assess(_finding("x", _ref("approved_statement.txt", 1)))
    email = assess(_finding("x", _ref("vendor_email.txt", 1)))
    assert {c.name: c.value for c in approved.factors}["authority"] == pytest.approx(1.0)
    assert {c.name: c.value for c in email.factors}["authority"] == pytest.approx(0.4)
    assert approved.value > email.value


def test_a_date_missing_from_the_cited_line_costs_temporal_consistency() -> None:
    finding = _finding("Completion is 14 May 2026.", _ref("report.txt", 10))
    factor = {c.name: c for c in assess(finding, evidence_text=TEXT).factors}[
        "temporal_consistency"
    ]
    assert factor.value == 0.0
    assert "not found: 14 May 2026" in factor.reason


def test_an_unchecked_factor_carries_no_weight_and_says_so() -> None:
    confidence = assess(_finding("Completion is 30 April 2026.", _ref("report.txt", 10)))
    factor = {c.name: c for c in confidence.factors}["temporal_consistency"]
    assert not factor.assessed and factor.weight == 0.0
    _terms_add_up(confidence)
    assert any(
        line.startswith("Not counted: temporal consistency") for line in why(_with(confidence))
    )


def _with(confidence: Confidence) -> Finding:
    finding = _finding("Completion is 30 April 2026.", _ref("report.txt", 10))
    finding.confidence = confidence
    return finding


def test_a_disputed_line_is_penalised_but_the_contradiction_is_not() -> None:
    contradiction = _finding(
        "The report gives 30 April 2026; finance gives 14 May 2026.",
        _ref("report.txt", 10),
        _ref("finance.txt", 12),
        finding_id="F-001",
    )
    restated = _finding("Completion is 30 April 2026.", _ref("report.txt", 10), finding_id="F-002")
    findings = [contradiction, restated]
    type_statements(findings, comparative=True)
    rescore(findings, evidence_text=TEXT)
    assert contradiction.confidence.penalty == 0.0
    assert restated.confidence.penalty == pytest.approx(0.15)
    _terms_add_up(restated.confidence)
    assert any("Minus 0.15" in line and "F-001" in line for line in why(restated))


def test_the_classification_still_caps_it() -> None:
    finding = _finding("x", _ref("approved_a.txt", 1), _ref("approved_b.txt", 2), _ref("c.txt", 3))
    finding.classification = FindingClassification.INFERENCE
    confidence = assess(finding)
    assert confidence.value == pytest.approx(0.85)
    assert any(line.startswith("Capped at 0.85") for line in why(_capped(finding, confidence)))


def _capped(finding: Finding, confidence: Confidence) -> Finding:
    finding.confidence = confidence
    return finding


def test_nothing_resolved_is_zero() -> None:
    finding = Finding(
        finding_id="F-001",
        claim="x",
        evidence=[EvidenceRef(locator=SourceLocator(document_id="a.txt", row=1))],
    )
    assert assess(finding).value == 0.0


def test_why_names_what_kept_it_lower_largest_first() -> None:
    finding = _finding("The SoW lists a BOM.", _ref("sow.docx", 50))
    rescore([finding], evidence_text=TEXT)
    lines = why(finding)
    assert lines[-1].startswith("Not higher: authority") or any(
        line.startswith("Not higher: independence 0.60") for line in lines
    )
    assert f"Confidence {finding.confidence.value:.2f}." in lines
    costs = [float(line.split(" cost ")[1].split(" ")[0]) for line in lines if " cost " in line]
    assert costs == sorted(costs, reverse=True)


def test_the_report_line_adds_up() -> None:
    finding = _finding("The SoW lists a BOM.", _ref("sow.docx", 50))
    rescore([finding], evidence_text=TEXT)
    line = finding.confidence.explain()
    assert line.startswith(f"{finding.confidence.value:.2f} = resolved 1.00 x ")
    assert "verification 0." in line


# --- the evidence chain ---------------------------------------------------------------------------


def test_the_chain_runs_from_claim_to_conclusion() -> None:
    run_id = new_run_id()
    finding = _finding("The SoW lists a BOM.", _ref("sow.docx", 50))
    finding.verification = VerificationResult(
        status=VerificationStatus.SUPPORTED,
        confidence=0.9,
        verifier="composite",
        opinions=[
            VerifierOpinion(verifier="baseline", status=VerificationStatus.SUPPORTED),
            VerifierOpinion(verifier="member4", status=VerificationStatus.SUPPORTED),
        ],
    )
    finding.proposed_type = "FACT"
    type_statements([finding], comparative=False)
    rescore([finding], evidence_text=TEXT)
    result = MissionResult(
        run_id=run_id,
        objective=Objective(text="What does the SoW deliver?"),
        findings=[finding],
        evidence_text={"sow.docx:r50": TEXT["sow.docx:r50"]},
        knowledge=KnowledgeSnapshot(
            entities=[KnowledgeEntity(entity_id="ENT-1", name="SoW", entity_type="OTHER")],
            claims=[
                KnowledgeClaim(
                    claim_id="CLM-1",
                    entity_id="ENT-1",
                    attribute="deliverable",
                    value="Bill of Material",
                    source="sow.docx:r50",
                    document_id="sow.docx",
                    line=50,
                )
            ],
        ),
    )
    created = ExecutionEvent(
        run_id=run_id,
        event_type=EventType.FINDING_CREATED,
        t_offset_ms=10,
        payload={"claim": finding.claim},
        finding_id="F-001",
    )
    chain = finding_chain(
        run_id, finding, result, {"sow.docx": "EV-000027"}, {"sow.docx": "OFFICIAL"}, [created]
    )

    assert [s.kind for s in chain.steps] == [
        "CLAIM",
        "EVIDENCE",
        "EXTRACTION",
        "REASONING",
        "VERIFICATION",
        "CONCLUSION",
    ]
    [cited] = chain.evidence
    assert (cited.evidence_id, cited.authority) == ("EV-000027", "Official document")
    assert cited.text == "Deliverables include a Bill of Material (BOM)."
    assert cited.extractions == ["SoW.deliverable = Bill of Material"]
    assert "proposed as FACT; ruled SOURCE_CLAIM" in chain.steps[3].detail
    assert "baseline: SUPPORTED; member4: SUPPORTED" in chain.steps[4].detail
    assert chain.steps[5].title == f"SOURCE_CLAIM, confidence {finding.confidence.value:.2f}"
    assert chain.why == why(finding)


def test_a_rejected_finding_is_capped_and_says_why() -> None:
    """Measured: without the cap a rejected one-document claim still read 0.47."""
    finding = _finding(
        "The SoW lists a BOM.", _ref("sow.docx", 50), status=VerificationStatus.UNSUPPORTED
    )
    rescore([finding], evidence_text=TEXT)
    assert finding.confidence.value == pytest.approx(0.3)
    assert "Capped at 0.30: the verifier found it unsupported." in why(finding)


def test_two_verified_documents_outrank_one() -> None:
    """Measured on the recorded runs: verified two-document findings were classified INFERENCE (not
    decomposed), capped at 0.85, and ranked below verified one-document ones (0.86-0.89)."""
    one = _finding("The SoW lists a BOM.", _ref("sow.docx", 50), finding_id="F-001")
    two = _finding(
        "Both list a BOM.", _ref("sow.docx", 50), _ref("annex.pdf", 3), finding_id="F-002"
    )
    two.elements = []
    two.classification = two.classify()
    assert two.classification is FindingClassification.INFERENCE
    findings = [one, two]
    type_statements(findings, comparative=False)
    rescore(findings, evidence_text=TEXT)
    assert two.classification is FindingClassification.FACT
    assert two.confidence.value > one.confidence.value
