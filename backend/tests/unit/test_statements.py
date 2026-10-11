"""Phase 45: statement types and source authority.

Every finding says what kind of statement it is, by rules over its evidence: one document makes a
SOURCE_CLAIM, never a FACT; a FACT needs two; a disagreement with both values cited is a
CONTRADICTION, and the report names both sides' authority without choosing between them.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from httpx import ASGITransport, AsyncClient

from app.api.app import create_app
from app.core.config import get_settings
from app.evidence import authority
from app.evidence.authority import authority_map, tier_for_name
from app.intelligence.reasoning.conflict_findings import conflict_findings
from app.intelligence.reasoning.statements import proposal, type_statement, type_statements
from app.intelligence.synthesis.engine import _finding_line, statement_text
from app.schemas.evidence import ClaimElement, EvidenceRef, ResolutionStatus, SourceLocator
from app.schemas.execution import Observation
from app.schemas.finding import Finding, FindingClassification, StatementType
from app.schemas.knowledge import ClaimConflict, ConflictKind, ConflictSide, KnowledgeSnapshot
from app.schemas.verification import VerificationResult, VerificationStatus


def _ref(document: str, row: int, *, resolved: bool = True) -> EvidenceRef:
    return EvidenceRef(
        evidence_id=f"E-{row:03d}" if resolved else None,
        locator=SourceLocator(document_id=document, document_name=document, row=row),
        resolution=ResolutionStatus.RESOLVED if resolved else ResolutionStatus.UNRESOLVED,
    )


def _finding(claim: str, *refs: EvidenceRef, proposed: str = "") -> Finding:
    """A finding whose one element is supported when everything it cites resolved - the state the
    verifier's decomposition leaves a fully cited claim in."""
    supported = bool(refs) and all(r.is_resolved for r in refs)
    finding = Finding(
        finding_id="F-001",
        claim=claim,
        evidence=list(refs),
        proposed_type=proposed,
        elements=[ClaimElement(text=claim, supported=supported)],
    )
    finding.classification = finding.classify()
    return finding


# --- the evidence basis ---------------------------------------------------------------------------


def test_nothing_resolved_is_unknown() -> None:
    finding = _finding("x", _ref("a.txt", 1, resolved=False))
    assert type_statement(finding, comparative=False) == (StatementType.UNKNOWN,) * 2


def test_a_partly_resolved_finding_is_a_hypothesis() -> None:
    finding = _finding("x", _ref("a.txt", 1), _ref("b.txt", 2, resolved=False))
    assert type_statement(finding, comparative=False)[0] is StatementType.HYPOTHESIS


def test_one_document_is_a_source_claim_however_many_lines() -> None:
    finding = _finding("The SoW lists a BOM.", _ref("sow.docx", 50), _ref("sow.docx", 51))
    assert type_statement(finding, comparative=False) == (StatementType.SOURCE_CLAIM,) * 2


def test_two_documents_make_a_fact() -> None:
    finding = _finding("Both name MDL.", _ref("a.txt", 1), _ref("b.txt", 2))
    assert finding.classification is FindingClassification.FACT
    assert type_statement(finding, comparative=False) == (StatementType.FACT,) * 2


def test_two_documents_a_verifier_confirmed_are_a_fact() -> None:
    """Measured on vega_start_corroborated: two documents agreeing on a start date, the claim
    verified against both lines, but not decomposed into supported elements."""
    finding = Finding(
        finding_id="F-001",
        claim="Project Vega starts on 6 April 2026.",
        evidence=[_ref("statement.txt", 6), _ref("finance.txt", 4)],
        verification=VerificationResult(status=VerificationStatus.SUPPORTED, confidence=0.9),
    )
    finding.classification = finding.classify()
    assert finding.classification is FindingClassification.INFERENCE
    assert type_statement(finding, comparative=False)[0] is StatementType.FACT


def test_the_candidate_s_default_unknown_is_no_proposal() -> None:
    """The model leaving its classification at the default must not override the evidence."""
    finding = _finding("x", _ref("a.txt", 1), _ref("b.txt", 2), proposed="UNKNOWN")
    assert type_statement(finding, comparative=False)[0] is StatementType.FACT


def test_two_documents_with_a_reasoning_step_are_an_inference() -> None:
    finding = _finding("x", _ref("a.txt", 1), _ref("b.txt", 2))
    finding.classification = FindingClassification.INFERENCE
    assert type_statement(finding, comparative=False)[0] is StatementType.INFERENCE


# --- the model proposes; the stricter answer wins -------------------------------------------------


def test_a_model_calling_one_document_a_fact_gets_a_source_claim() -> None:
    """Phase 45's acceptance: no single-source FACT."""
    finding = _finding("The SoW lists a BOM.", _ref("sow.docx", 50), proposed="FACT")
    assert type_statement(finding, comparative=False)[0] is StatementType.SOURCE_CLAIM


def test_a_more_cautious_model_is_believed_and_the_basis_kept() -> None:
    finding = _finding("x", _ref("a.txt", 1), _ref("b.txt", 2), proposed="hypothesis")
    assert type_statement(finding, comparative=False) == (
        StatementType.HYPOTHESIS,
        StatementType.FACT,
    )


def test_a_proposed_risk_is_kept_with_what_it_rests_on() -> None:
    finding = _finding("No penetration test.", _ref("sow.docx", 9), proposed="RISK")
    type_statements([finding], comparative=False)
    assert (finding.statement_type, finding.statement_basis) == (
        StatementType.RISK,
        StatementType.SOURCE_CLAIM,
    )
    assert statement_text(finding) == "RISK on SOURCE_CLAIM"


def test_a_proposed_risk_with_nothing_resolved_is_not_a_risk() -> None:
    finding = _finding("x", _ref("a.txt", 1, resolved=False), proposed="RISK")
    assert type_statement(finding, comparative=False)[0] is StatementType.UNKNOWN


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("FACT", StatementType.FACT),
        ("source claim", StatementType.SOURCE_CLAIM),
        ("Source-Claim", StatementType.SOURCE_CLAIM),
        ("conflict", StatementType.CONTRADICTION),
        ("recommendation", StatementType.RECOMMENDATION),
        ("", None),
        ("very sure", None),
    ],
)
def test_proposals_are_read_from_how_models_write_them(
    raw: str, expected: StatementType | None
) -> None:
    assert proposal(raw) is expected


# --- contradictions -------------------------------------------------------------------------------

CLAIM = "The report gives 30 April 2026 for completion; the finance sheet gives 14 May 2026."


def test_two_cited_values_in_a_comparison_are_a_contradiction() -> None:
    finding = _finding(CLAIM, _ref("report.txt", 10), _ref("finance.txt", 12))
    assert type_statement(finding, comparative=True) == (
        StatementType.CONTRADICTION,
        StatementType.FACT,
    )


def test_a_report_contradicting_itself_is_a_contradiction_on_one_source() -> None:
    finding = _finding(CLAIM, _ref("report.txt", 10), _ref("report.txt", 15))
    assert type_statement(finding, comparative=True) == (
        StatementType.CONTRADICTION,
        StatementType.SOURCE_CLAIM,
    )


def test_one_value_twice_is_agreement_not_a_contradiction() -> None:
    claim = "Both give 30 April 2026 for completion: 30 April 2026."
    finding = _finding(claim, _ref("report.txt", 10), _ref("finance.txt", 12))
    assert type_statement(finding, comparative=True)[0] is StatementType.FACT


def test_two_values_outside_a_comparison_need_a_proposal() -> None:
    finding = _finding(CLAIM, _ref("report.txt", 10), _ref("finance.txt", 12))
    assert type_statement(finding, comparative=False)[0] is StatementType.FACT
    finding.proposed_type = "CONTRADICTION"
    assert type_statement(finding, comparative=False)[0] is StatementType.CONTRADICTION


def test_a_contradiction_needs_both_sides_resolved() -> None:
    finding = _finding(CLAIM, _ref("report.txt", 10), _ref("finance.txt", 12, resolved=False))
    assert type_statement(finding, comparative=True)[0] is StatementType.HYPOTHESIS


def test_the_graph_s_conflicts_become_contradictions() -> None:
    conflict = ClaimConflict(
        conflict_id="CON-001",
        entity_id="ENT-1",
        entity_name="Project Aurora",
        attribute="completion_date",
        kind=ConflictKind.DATE,
        sides=[
            ConflictSide(value="30 April 2026", claim_ids=["CLM-1"], sources=["report.txt:r10"]),
            ConflictSide(value="14 May 2026", claim_ids=["CLM-2"], sources=["finance.txt:r12"]),
        ],
    )
    observations = [
        Observation(
            task_id="task_001",
            task_type="extract_claims",
            content="1 conflict",
            sources=["report.txt:r10", "finance.txt:r12"],
        )
    ]
    [finding] = conflict_findings(
        KnowledgeSnapshot(conflicts=[conflict]), [], observations, comparative=True
    )
    type_statements([finding], comparative=False)
    assert finding.statement_type is StatementType.CONTRADICTION


# --- the invariant --------------------------------------------------------------------------------


def test_a_single_source_fact_cannot_be_constructed() -> None:
    with pytest.raises(ValueError, match="two documents"):
        Finding(
            finding_id="F-001",
            claim="x",
            evidence=[_ref("a.txt", 1), _ref("a.txt", 2)],
            statement_type=StatementType.FACT,
        )


# --- source authority -----------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("name", "tier"),
    [
        ("draft_email_to_vendor.txt", "DRAFT"),
        ("vendor_email.eml", "CORRESPONDENCE"),
        ("approved_statement.txt", "APPROVED"),
        ("Annexure-I-SoW_iDEX_71 (1).docx", "OFFICIAL"),
        ("2. Detailed Project Timeline.pdf", "REPORT"),
        ("6. Return on Investment.pdf", "UNASSESSED"),
        ("shipment_driver_note.txt", "CORRESPONDENCE"),
    ],
)
def test_intake_rules_give_a_tier_from_the_name(name: str, tier: str) -> None:
    assert tier_for_name(name)[0] == tier


def test_the_rule_that_matched_is_the_reason() -> None:
    assert tier_for_name("draft_budget.txt")[1] == 'set at intake: the name contains "draft"'


def test_the_locker_s_tier_wins_over_the_rules() -> None:
    assert authority_map(["a_draft.txt", "b.txt"], {"a_draft.txt": "APPROVED"}) == {
        "a_draft.txt": "APPROVED",
        "b.txt": "UNASSESSED",
    }


def test_with_no_authority_config_every_source_is_unassessed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(type(get_settings()), "agent_dir", property(lambda _self: tmp_path))
    assert authority.get_authority_config().default == "UNASSESSED"
    assert tier_for_name("approved_draft.txt")[0] == "UNASSESSED"


def test_a_contradiction_line_names_both_sides_authority_and_resolves_nothing() -> None:
    claim = "The approved statement gives 250,000; the draft email gives 300,000."
    finding = _finding(claim, _ref("approved_statement.txt", 4), _ref("draft_email.txt", 2))
    type_statements([finding], comparative=True)
    line = _finding_line(finding, {"approved_statement.txt": "APPROVED"})
    assert "(CONTRADICTION" in line
    assert "approved_statement.txt:r4 [Approved or signed]" in line
    assert "draft_email.txt:r2 [Draft]" in line


def test_an_ordinary_finding_line_carries_its_type() -> None:
    finding = _finding("The SoW lists a BOM.", _ref("sow.docx", 50))
    assert "(SOURCE_CLAIM, confidence" in _finding_line(finding)


# --- the API --------------------------------------------------------------------------------------


async def _client() -> AsyncClient:
    return AsyncClient(transport=ASGITransport(app=create_app()), base_url="http://test")


async def test_an_upload_gets_its_tier_and_a_person_can_change_it() -> None:
    async with await _client() as client:
        uploaded = (
            await client.post(
                "/api/v1/documents", files=[("files", ("draft_email.txt", b"Budget 300,000.\n"))]
            )
        ).json()[0]
        evidence_id = uploaded["evidence_id"]
        item = (await client.get(f"/api/v1/evidence/{evidence_id}")).json()["item"]
        assert item["authority"] == "DRAFT"

        changed = await client.patch(
            f"/api/v1/evidence/{evidence_id}",
            json={"authority": "APPROVED", "authority_reason": "signed copy received"},
            headers={"X-Jarvis-User": "reviewer-2"},
        )
        assert changed.status_code == 200
        assert changed.json()["authority"] == "APPROVED"
        assert changed.json()["authority_reason"] == "set by reviewer-2: signed copy received"

        detail = (await client.get(f"/api/v1/evidence/{evidence_id}")).json()
        [event] = [e for e in detail["custody"] if e["action"] == "METADATA_CHANGED"]
        assert event["actor"] == "reviewer-2"
        assert event["details"]["authority"] == {"from": "DRAFT", "to": "APPROVED"}


async def test_an_unknown_tier_is_refused() -> None:
    async with await _client() as client:
        uploaded = (
            await client.post("/api/v1/documents", files=[("files", ("a.txt", b"x\n"))])
        ).json()[0]
        response = await client.patch(
            f"/api/v1/evidence/{uploaded['evidence_id']}", json={"authority": "GOSPEL"}
        )
        assert response.status_code == 422
        assert response.json()["error_code"] == "UNKNOWN_AUTHORITY_TIER"


async def test_the_tiers_are_listed_highest_first() -> None:
    async with await _client() as client:
        tiers = (await client.get("/api/v1/evidence/authority")).json()
    assert [t["id"] for t in tiers][:2] == ["APPROVED", "OFFICIAL"]
    assert "UNASSESSED" in {t["id"] for t in tiers}


# --- the evaluation checks it (Phase 45) ----------------------------------------------------------


def test_a_scenario_reports_a_statement_type_no_finding_carries() -> None:
    from app.evaluation.metrics import (
        MetricSet,
        ScenarioExpectation,
        ScenarioOutcome,
        missed_statement_types,
    )
    from app.evaluation.report import EvalReport, ScenarioReport

    expectation = ScenarioExpectation(
        scenario_id="vega_authority_conflict",
        objective="x",
        expected_statement_types=["CONTRADICTION"],
    )
    typed = _finding("The SoW lists a BOM.", _ref("sow.docx", 50))
    type_statements([typed], comparative=False)
    outcome = ScenarioOutcome(scenario_id="vega_authority_conflict", findings=[typed])
    assert missed_statement_types(expectation, outcome) == ["CONTRADICTION"]
    assert missed_statement_types(expectation, ScenarioOutcome(scenario_id="v")) == []

    report = EvalReport(
        suite="all",
        scenarios=[
            ScenarioReport(
                scenario_id="vega_authority_conflict",
                metrics=MetricSet(),
                findings=1,
                missed_statement_types=["CONTRADICTION"],
            )
        ],
    )
    assert "vega_authority_conflict: no finding is typed CONTRADICTION" in report.build_failures()
