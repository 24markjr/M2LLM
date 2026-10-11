"""Phase 47: competing explanations, tested against the findings, ranked by computed support.

The model proposes explanations and says which findings bear on them; it never ranks them. Support
is the confidence of the verified findings for an explanation minus those against it, and a question
the findings cannot settle is left open - with what would decide it and where to look next.
"""

from __future__ import annotations

import json

import pytest

from app.evaluation.metrics import (
    MetricSet,
    ScenarioExpectation,
    ScenarioOutcome,
    concluded_prematurely,
    open_hypotheses,
)
from app.evaluation.report import EvalReport, ScenarioReport
from app.intelligence.hypotheses.engine import (
    HypothesisEngine,
    HypothesisSettings,
    rank,
    search_leads,
    wants_explanation,
)
from app.llm.echo import EchoProvider
from app.schemas.evidence import EvidenceRef, ResolutionStatus, SourceLocator
from app.schemas.finding import Confidence, Finding
from app.schemas.hypothesis import (
    FindingRelation,
    Hypothesis,
    HypothesisSet,
    HypothesisStatus,
    NextEvidenceKind,
    Relation,
)
from app.schemas.verification import VerificationResult, VerificationStatus

DOCUMENTS = {
    "lyra_incident_log.txt": (
        "LYRA BILLING - INCIDENT LOG\n"
        "02:10 Change CHG-118 deployed to the billing server.\n"
        "02:13 Facilities report a power dip on rack B.\n"
        "02:14 The billing server stopped answering requests.\n"
    ),
    "lyra_facilities_note.txt": (
        "FACILITIES NOTE\nA brief power dip was recorded on rack B at 02:13.\n"
        "The UPS log for rack B is held by the vendor and is not attached.\n"
    ),
}
OBJECTIVE = "Why did the Lyra billing server go offline on 3 March 2026?"


def _finding(finding_id: str, claim: str, confidence: float = 0.9) -> Finding:
    ref = EvidenceRef(
        evidence_id="E-001",
        locator=SourceLocator(document_id="lyra_incident_log.txt", row=2),
        resolution=ResolutionStatus.RESOLVED,
    )
    finding = Finding(
        finding_id=finding_id,
        claim=claim,
        evidence=[ref],
        verification=VerificationResult(status=VerificationStatus.SUPPORTED, confidence=0.9),
    )
    finding.classification = finding.classify()
    finding.confidence = Confidence.compute(
        refs=[ref], source_agreement=confidence, classification=finding.classification
    )
    return finding


FINDINGS = [
    _finding("F-001", "Change CHG-118 was deployed at 02:10, four minutes before the outage."),
    _finding("F-002", "A power dip was recorded on rack B at 02:13."),
]

PROPOSED = json.dumps(
    {
        "hypotheses": [
            {
                "statement": "The configuration change CHG-118 caused the outage.",
                "decisive_evidence": "the billing server's network log after 02:10",
                "search_query": "CHG-118 network settings",
            },
            {
                "statement": "The power dip on rack B caused the outage.",
                "decisive_evidence": "the UPS log for rack B at 02:13",
                "search_query": "UPS log rack B",
            },
        ]
    }
)


def _tested(*verdicts: tuple[int, str, str]) -> str:
    return json.dumps(
        {"verdicts": [{"hypothesis": h, "finding_id": f, "relation": r} for h, f, r in verdicts]}
    )


# --- when it runs ---------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("objective", "explains"),
    [
        ("Why did the Lyra billing server go offline?", True),
        ("Determine the root cause of the delay.", True),
        ("What happened to Shipment 4821?", True),
        ("Explain the budget overrun.", True),
        ("Compare the two reports and identify contradictions in the dates.", False),
        ("Determine whether the invoice and delivery confirmation contradict each other.", False),
    ],
)
def test_only_an_explanation_question_gets_hypotheses(objective: str, explains: bool) -> None:
    assert wants_explanation(objective) is explains


async def test_a_comparison_question_costs_no_model_call() -> None:
    provider = EchoProvider(responses={})
    result = await HypothesisEngine(provider).run(
        "Compare the reports for contradictions.", FINDINGS, [], DOCUMENTS
    )
    assert result.skipped_reason == "the objective does not ask for an explanation"
    assert provider.calls == []


# --- ranking is computed --------------------------------------------------------------------------


async def test_findings_that_fit_both_explanations_leave_the_question_open() -> None:
    """The Lyra scenario: each finding supports one explanation; neither is ahead by the margin."""
    provider = EchoProvider(
        responses={
            "hypotheses": [
                PROPOSED,
                _tested((1, "F-001", "SUPPORTS"), (2, "F-002", "SUPPORTS")),
            ]
        }
    )
    result = await HypothesisEngine(provider).run(OBJECTIVE, FINDINGS, [], DOCUMENTS)

    assert len(provider.calls) == 2, "two model calls at most"
    assert result.llm_calls == 2
    assert not result.determined
    assert [h.status for h in result.hypotheses] == [HypothesisStatus.OPEN] * 2
    assert result.summary.startswith("Undetermined: 2 explanation(s) remain open")
    assert all(h.support == pytest.approx(0.9) for h in result.hypotheses)


async def test_an_open_explanation_gets_leads_or_a_request() -> None:
    provider = EchoProvider(responses={"hypotheses": [PROPOSED, _tested((1, "F-001", "SUPPORTS"))]})
    result = await HypothesisEngine(provider).run(OBJECTIVE, FINDINGS, [], DOCUMENTS)
    by_statement = {h.statement: h for h in result.hypotheses}

    power = by_statement["The power dip on rack B caused the outage."].next_evidence
    assert power is not None and power.kind is NextEvidenceKind.SEARCH
    assert power.leads[0].locator == "lyra_facilities_note.txt:r3"
    assert "UPS log" in power.leads[0].text

    change = by_statement["The configuration change CHG-118 caused the outage."]
    assert change.status is HypothesisStatus.SUPPORTED or change.next_evidence is not None


def test_one_explanation_clearly_ahead_is_supported() -> None:
    settings = HypothesisSettings()
    ahead = Hypothesis(
        hypothesis_id="H-1",
        statement="a",
        supporting=[
            FindingRelation(finding_id="F-001", relation=Relation.SUPPORTS, confidence=0.9),
        ],
    )
    behind = Hypothesis(hypothesis_id="H-2", statement="b")
    ordered, determined, summary = rank([behind, ahead], settings)
    assert ordered[0] is ahead and determined
    assert ahead.status is HypothesisStatus.SUPPORTED
    assert "0.90 ahead" in ahead.status_reason
    assert summary == "Supported: a"


def test_a_contradicted_explanation_is_rejected_and_never_supported() -> None:
    settings = HypothesisSettings()
    refuted = Hypothesis(
        hypothesis_id="H-1",
        statement="a",
        contradicting=[
            FindingRelation(finding_id="F-001", relation=Relation.CONTRADICTS, confidence=0.9)
        ],
    )
    other = Hypothesis(hypothesis_id="H-2", statement="b")
    _, determined, _ = rank([refuted, other], settings)
    assert refuted.status is HypothesisStatus.REJECTED
    assert not determined and other.status is HypothesisStatus.OPEN


async def test_unverified_findings_and_invented_ids_count_for_nothing() -> None:
    unverified = _finding("F-003", "The UPS failed.")
    unverified.verification = None
    provider = EchoProvider(
        responses={
            "hypotheses": [
                PROPOSED,
                _tested(
                    (2, "F-003", "SUPPORTS"),
                    (2, "F-999", "SUPPORTS"),
                    (7, "F-001", "SUPPORTS"),
                    (1, "F-001", "SUPPORTS"),
                    (1, "F-001", "SUPPORTS"),
                ),
            ]
        }
    )
    result = await HypothesisEngine(provider).run(OBJECTIVE, [*FINDINGS, unverified], [], DOCUMENTS)
    change = next(h for h in result.hypotheses if "CHG-118" in h.statement)
    power = next(h for h in result.hypotheses if "power" in h.statement)
    assert [r.finding_id for r in change.supporting] == ["F-001"], "each pair once"
    assert power.supporting == []


async def test_one_proposal_is_not_a_competition() -> None:
    single = json.dumps({"hypotheses": [{"statement": "The change caused it."}]})
    result = await HypothesisEngine(EchoProvider(responses={"hypotheses": [single]})).run(
        OBJECTIVE, FINDINGS, [], DOCUMENTS
    )
    assert result.hypotheses == []
    assert "competing explanations need 2" in result.skipped_reason


def test_leads_need_half_the_query_words() -> None:
    leads = search_leads("UPS log rack B", DOCUMENTS, {}, 3)
    assert leads[0].locator == "lyra_facilities_note.txt:r3"
    assert search_leads("quarterly revenue forecast", DOCUMENTS, {}, 3) == []


# --- the evaluation measures premature conclusions ------------------------------------------------


def _set(*statuses: HypothesisStatus) -> HypothesisSet:
    return HypothesisSet(
        hypotheses=[
            Hypothesis(hypothesis_id=f"H-{i}", statement=str(i), status=s)
            for i, s in enumerate(statuses, start=1)
        ]
    )


def test_closing_an_undetermined_question_is_a_premature_conclusion() -> None:
    expectation = ScenarioExpectation(scenario_id="lyra", objective="x", expect_open_hypotheses=2)
    left_open = ScenarioOutcome(
        scenario_id="lyra", hypotheses=_set(HypothesisStatus.OPEN, HypothesisStatus.OPEN)
    )
    closed = ScenarioOutcome(
        scenario_id="lyra",
        hypotheses=_set(HypothesisStatus.SUPPORTED, HypothesisStatus.OPEN),
    )
    assert open_hypotheses(left_open) == 2 and not concluded_prematurely(expectation, left_open)
    assert concluded_prematurely(expectation, closed)
    assert concluded_prematurely(expectation, ScenarioOutcome(scenario_id="lyra"))

    report = EvalReport(
        suite="all",
        scenarios=[
            ScenarioReport(
                scenario_id="lyra",
                metrics=MetricSet(),
                expected_open_hypotheses=2,
                open_hypotheses=1,
                premature_conclusion=True,
            ),
            ScenarioReport(scenario_id="other", metrics=MetricSet()),
        ],
    )
    assert report.premature_conclusion_rate == 1.0
    assert any("an undetermined question was closed" in f for f in report.build_failures())
    assert EvalReport(suite="all").premature_conclusion_rate is None
