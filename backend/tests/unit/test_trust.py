"""Phase 26: Member 4's trust layer, ported.

Covers T1-T6 and T13-T15 of `.claude/integrations/teammate-port.md`: TF-IDF parity with
scikit-learn, every branch of the verifier, the conflict rule and its three deviations, answer
evaluation, the adapter onto JARVIS's verification vocabulary, the composite verifier, and the
benchmark reproducing the original's data and score.
"""

from __future__ import annotations

import json

import pytest

from app.evaluation.trust import generate, run_trust_benchmark, trust_dir
from app.integrations.verification import (
    BaselineVerifier,
    CompositeVerifier,
    LexicalVerifier,
    build_request,
    build_verification_provider,
)
from app.intelligence.trust.answer import evaluate_answer, split_into_claims
from app.intelligence.trust.lexical import verify_claim
from app.intelligence.trust.tfidf import (
    ENGLISH_STOP_WORDS,
    relevance_scores,
    tfidf_cosine,
    word_overlap,
)
from app.llm.echo import EchoProvider
from app.schemas.common import SourceLocator
from app.schemas.evidence import EvidenceRef, ResolutionStatus
from app.schemas.finding import Finding
from app.schemas.trust import EvidenceText, LexicalThresholds, TrustStatus
from app.schemas.verification import (
    IssueType,
    VerificationRequest,
    VerificationResult,
    VerificationStatus,
)

SHIPPING = [
    EvidenceText(
        source="shipping_report_a.pdf:p4",
        content=(
            "Shipment 4821 arrived on 14 September at the Mumbai warehouse. "
            "It was received by Rahul Sharma."
        ),
    ),
    EvidenceText(
        source="shipping_report_b.pdf:p7",
        content=(
            "Shipment 4821 arrived on 16 September at the Mumbai facility, "
            "according to security logs."
        ),
    ),
]


# --- T1/T2: TF-IDF ----------------------------------------------------------------


def test_tfidf_matches_scikit_learn_reference_values() -> None:
    """Reference values from scikit-learn 1.9.1, `TfidfVectorizer(stop_words="english")`.

    The full 60-case x 58-document parity check measured a largest difference of 4.4e-16; these
    two pin it without needing scikit-learn installed.
    """
    first = tfidf_cosine(
        "Shipment 4821 arrived on 14 September.",
        [
            "Shipment 4821 arrived on 14 September at the Mumbai warehouse.",
            "Invoice 9012 was issued by ABC Logistics.",
        ],
    )
    second = tfidf_cosine(
        "The incident occurred at 11:40 AM.",
        ["Incident occurred at 11:40 AM.", "The incident occurred at 1:15 PM."],
    )
    assert first == pytest.approx([0.768875170785, 0.0], abs=1e-9)
    assert second == pytest.approx([1.0, 0.311917248016], abs=1e-9)


def test_the_stop_word_list_is_scikit_learns() -> None:
    assert len(ENGLISH_STOP_WORDS) == 318
    assert {"the", "at", "on", "was"} <= ENGLISH_STOP_WORDS


def test_an_empty_vocabulary_returns_none_and_falls_back_to_overlap() -> None:
    """The only case the original reached word overlap with scikit-learn installed."""
    assert tfidf_cosine("the of and", ["it was", "on the"]) is None
    assert relevance_scores("the of and", ["the of", "x"]) == [
        word_overlap("the of and", "the of"),
        word_overlap("the of and", "x"),
    ]


def test_overlap_is_never_used_when_tfidf_can_score() -> None:
    """The fallback marked a wrong date SUPPORTED at 0.83. It must not be reachable here."""
    scores = relevance_scores(
        "Shipment 4821 arrived on 20 September.", [e.content for e in SHIPPING]
    )
    assert all(s < 0.4 for s in scores)


# --- T3/T4: the verifier ----------------------------------------------------------


def test_an_empty_pool_is_insufficient_evidence() -> None:
    assert verify_claim("anything", []).status is TrustStatus.INSUFFICIENT_EVIDENCE


def test_nothing_relevant_is_insufficient_evidence() -> None:
    verdict = verify_claim("The employee's 2021 salary was 50000.", SHIPPING)
    assert verdict.status is TrustStatus.INSUFFICIENT_EVIDENCE
    assert verdict.scored and not any(s.relevant for s in verdict.scored)


@pytest.mark.parametrize(
    ("claim", "status"),
    [
        # The four probes from the scan, 2026-10-03. The second is the deviation: the original
        # returned UNSUPPORTED because it could not see dates.
        ("Shipment 4821 arrived on 14 September.", TrustStatus.SUPPORTED),
        ("Shipment 4821 arrived on 20 September.", TrustStatus.UNSUPPORTED),
        (
            "Shipment 4821 arrived on 14 September and 16 September "
            "according to different reports.",
            TrustStatus.SUPPORTED,
        ),
        ("Shipment 4821 was not delivered to Mumbai.", TrustStatus.UNSUPPORTED),
    ],
)
def test_the_shipment_probes(claim: str, status: TrustStatus) -> None:
    assert verify_claim(claim, SHIPPING).status is status


def test_a_wrong_date_on_a_shared_id_is_contradicted_when_close_enough() -> None:
    """Deviation A4. The original only compared clock times, so this was never CONTRADICTED."""
    evidence = [
        EvidenceText(source="a.txt:r1", content="Shipment 4821 arrived on 14 September."),
    ]
    verdict = verify_claim("Shipment 4821 arrived on 20 September.", evidence)
    assert verdict.status is TrustStatus.CONTRADICTED
    assert verdict.contradicting == ["a.txt:r1"]
    assert "dates" in verdict.reasoning and "4821" in verdict.reasoning


def test_a_different_time_on_a_shared_id_is_contradicted() -> None:
    evidence = [
        EvidenceText(source="a.txt:r1", content="Shipment 1004 was processed at 9:15 AM."),
    ]
    verdict = verify_claim("Shipment 1004 was processed at 11:40 AM.", evidence)
    assert verdict.status is TrustStatus.CONTRADICTED
    assert "times" in verdict.reasoning


def test_without_a_shared_id_a_different_time_is_not_a_contradiction() -> None:
    """Member 4's own `contradiction_test.py` demo, unchanged. It returns SUPPORTED.

    When Member 4 added the shared-identifier safeguard, this demo's claim stopped having an
    identifier to share, so it no longer demonstrates a contradiction. Their original prints
    SUPPORTED too (run 2026-10-03). Kept as the original behaves; the test above is the
    working demonstration.
    """
    evidence = [
        EvidenceText(source="incident_report.pdf:p1", content="Incident occurred at 11:40 AM."),
        EvidenceText(
            source="employee_statement.docx:p1", content="The incident occurred at 1:15 PM."
        ),
    ]
    verdict = verify_claim("The incident occurred at 11:40 AM.", evidence)
    assert verdict.status is TrustStatus.SUPPORTED
    assert verdict.supporting == ["incident_report.pdf:p1"]


def test_a_time_without_am_pm_does_not_conflict_with_the_same_time_with_it() -> None:
    """The original compared "11:40" and "11:40am" as strings."""
    evidence = [EvidenceText(source="a.txt:r1", content="Shipment 1004 was processed at 11:40.")]
    verdict = verify_claim("Shipment 1004 was processed at 11:40 AM.", evidence)
    assert verdict.status is TrustStatus.SUPPORTED


def test_a_shared_year_is_not_a_shared_id() -> None:
    """The original read "2026" as an identifier, so these two would have conflicted."""
    evidence = [
        EvidenceText(
            source="a.txt:r1", content="Milestone M1 requirements complete on 15 January 2026."
        )
    ]
    verdict = verify_claim("Milestone M4 production readiness on 30 April 2026.", evidence)
    assert verdict.status is not TrustStatus.CONTRADICTED


def test_the_conflict_rule_needs_relevance_above_its_threshold() -> None:
    evidence = [EvidenceText(source="a.txt:r1", content="Shipment 4821 arrived on 14 September.")]
    strict = LexicalThresholds(relevance=0.2, support=0.4, conflict=0.99)
    verdict = verify_claim("Shipment 4821 arrived on 20 September.", evidence, strict)
    assert verdict.status is not TrustStatus.CONTRADICTED


# --- T5: answer evaluation --------------------------------------------------------


def test_sentences_split_after_terminal_punctuation() -> None:
    assert split_into_claims("One. Two! Three?  ") == ["One.", "Two!", "Three?"]


def test_a_mixed_answer_is_partially_supported() -> None:
    """Member 4's own demo: one true sentence, one invented."""
    evidence = [
        EvidenceText(source="incident_report.pdf:p1", content="Incident occurred at 11:40 AM."),
        EvidenceText(
            source="shipping_report.pdf:p7", content="Shipment 4821 was recorded on 14 September."
        ),
    ]
    assessment = evaluate_answer(
        "The incident occurred at 11:40 AM. "
        "The employee responsible was later terminated for misconduct.",
        evidence,
    )
    assert assessment.overall is TrustStatus.PARTIALLY_SUPPORTED
    assert [c.status for c in assessment.claims] == [
        TrustStatus.SUPPORTED,
        TrustStatus.INSUFFICIENT_EVIDENCE,
    ]


def test_any_contradicted_sentence_contradicts_the_answer() -> None:
    evidence = [EvidenceText(source="a.txt:r1", content="Shipment 4821 arrived on 14 September.")]
    assessment = evaluate_answer(
        "Shipment 4821 arrived on 14 September. Shipment 4821 arrived on 20 September.", evidence
    )
    assert assessment.overall is TrustStatus.CONTRADICTED


def test_an_empty_answer_is_insufficient_evidence() -> None:
    assert evaluate_answer("   ", SHIPPING).overall is TrustStatus.INSUFFICIENT_EVIDENCE


# --- T6: the adapter onto JARVIS's vocabulary ---------------------------------------


def _ref(doc: str, row: int, *, resolved: bool = True) -> EvidenceRef:
    return EvidenceRef(
        locator=SourceLocator(document_id=doc, document_name=doc, row=row),
        resolution=ResolutionStatus.RESOLVED if resolved else ResolutionStatus.UNRESOLVED,
    )


def _request(claim: str, *pairs: tuple[str, int, str]) -> VerificationRequest:
    refs = [_ref(doc, row) for doc, row, _ in pairs]
    text = {f"{doc}:r{row}": f"{doc}:r{row}: {body}" for doc, row, body in pairs}
    return build_request(Finding(finding_id="F-001", claim=claim, evidence=refs), text)


async def test_lexical_supported_maps_to_supported() -> None:
    result = await LexicalVerifier().verify(
        _request("Shipment 4821 arrived on 14 September.", ("a.txt", 1, SHIPPING[0].content))
    )
    assert result.status is VerificationStatus.SUPPORTED
    assert result.verifier == "lexical"


async def test_lexical_contradicted_names_the_conflicting_source() -> None:
    result = await LexicalVerifier().verify(
        _request(
            "Shipment 4821 arrived on 20 September.",
            ("a.txt", 1, "Shipment 4821 arrived on 14 September."),
        )
    )
    assert result.status is VerificationStatus.CONTRADICTED
    assert result.issues[0].issue_type is IssueType.SOURCE_CONFLICT
    assert result.issues[0].element == "a.txt:r1"


async def test_insufficient_evidence_maps_to_inconclusive_never_a_pass() -> None:
    result = await LexicalVerifier().verify(
        _request("The 2021 salary was 50000.", ("a.txt", 1, SHIPPING[0].content))
    )
    assert result.status is VerificationStatus.INCONCLUSIVE
    assert not result.passed


async def test_no_resolved_evidence_is_unsupported_without_scoring() -> None:
    finding = Finding(finding_id="F-001", claim="x", evidence=[_ref("a.txt", 1, resolved=False)])
    result = await LexicalVerifier().verify(build_request(finding, {}))
    assert result.status is VerificationStatus.UNSUPPORTED
    assert result.issues[0].issue_type is IssueType.NO_EVIDENCE


async def test_the_locator_prefix_is_not_scored_as_evidence() -> None:
    """Evidence text arrives as "a.txt:r1: <line>". The locator must not count as a term."""
    request = _request("a.txt r1", ("a.txt", 1, "Completely unrelated sentence about weather."))
    result = await LexicalVerifier().verify(request)
    assert result.status is VerificationStatus.INCONCLUSIVE


# --- the composite verifier -----------------------------------------------------------


class _Fixed:
    """A model verifier that always returns one verdict."""

    def __init__(self, status: VerificationStatus) -> None:
        self.status = status

    async def verify(self, request: VerificationRequest) -> VerificationResult:
        failing = {VerificationStatus.UNSUPPORTED, VerificationStatus.CONTRADICTED}
        issues = []
        if self.status in failing:
            from app.schemas.verification import VerificationIssue

            issues = [
                VerificationIssue(issue_type=IssueType.EVIDENCE_MISMATCH, description="model")
            ]
        return VerificationResult(
            status=self.status, confidence=0.8, verifier="baseline", issues=issues
        )


_WRONG_DATE = (
    "Shipment 4821 arrived on 20 September.",
    ("a.txt", 1, "Shipment 4821 arrived on 14 September."),
)
_RIGHT_DATE = (
    "Shipment 4821 arrived on 14 September.",
    ("a.txt", 1, "Shipment 4821 arrived on 14 September."),
)


async def test_composite_rule_1_a_lexical_contradiction_wins() -> None:
    composite = CompositeVerifier(_Fixed(VerificationStatus.SUPPORTED), LexicalVerifier())
    result = await composite.verify(_request(*_WRONG_DATE))
    assert result.status is VerificationStatus.CONTRADICTED
    assert result.verifier == "composite"
    assert {o.verifier: o.status for o in result.opinions} == {
        "baseline": VerificationStatus.SUPPORTED,
        "lexical": VerificationStatus.CONTRADICTED,
    }


async def test_composite_rule_2_lexical_stands_in_when_the_model_cannot_decide() -> None:
    composite = CompositeVerifier(_Fixed(VerificationStatus.INCONCLUSIVE), LexicalVerifier())
    result = await composite.verify(_request(*_RIGHT_DATE))
    assert result.status is VerificationStatus.SUPPORTED
    assert result.degraded
    assert "lexical" in result.degraded_reason


async def test_composite_rule_3_lexical_support_never_overrides_a_model_rejection() -> None:
    composite = CompositeVerifier(_Fixed(VerificationStatus.UNSUPPORTED), LexicalVerifier())
    result = await composite.verify(_request(*_RIGHT_DATE))
    assert result.status is VerificationStatus.UNSUPPORTED
    assert not result.degraded


@pytest.mark.parametrize(
    ("name", "kind"),
    [
        ("lexical", LexicalVerifier),
        ("composite", CompositeVerifier),
        ("baseline", BaselineVerifier),
    ],
)
def test_the_provider_is_selected_by_setting(
    monkeypatch: pytest.MonkeyPatch, name: str, kind: type
) -> None:
    from app.core.config import VerificationProviderName, get_settings

    monkeypatch.setattr(get_settings(), "verification_provider", VerificationProviderName(name))
    assert isinstance(build_verification_provider(EchoProvider()), kind)


# --- T13-T15: the benchmark ----------------------------------------------------------


def test_the_generator_reproduces_member_4s_committed_data_exactly() -> None:
    corpus, cases = generate()
    committed_corpus = json.loads((trust_dir() / "evidence_corpus.json").read_text("utf-8"))
    committed_cases = json.loads((trust_dir() / "benchmark.json").read_text("utf-8"))
    assert corpus == committed_corpus
    assert cases == committed_cases
    assert (len(corpus), len(cases)) == (58, 60)


def test_the_benchmark_scores_what_the_original_scored() -> None:
    """60/60 and no false confidence, as Member 4's runner reported with scikit-learn."""
    report = run_trust_benchmark()
    assert report.accuracy == 1.0
    assert report.hallucination_rate == 0.0
    assert report.category_accuracy == {
        "contradiction": 1.0,
        "insufficient_evidence": 1.0,
        "supported": 1.0,
    }


# --- A15 / BUG-018: a claim cannot state a value its evidence does not contain --------


def test_a_date_no_evidence_contains_is_ungrounded() -> None:
    """The claim the model verifier approved in the Phase 25 audit, verbatim."""
    from app.intelligence.trust.specifics import ungrounded_specifics

    claim = (
        "The milestone report states that milestone r10 closes on 30 April 2026, but the "
        "project report states it closes on 28 April 2026"
    )
    evidence = [
        EvidenceText(
            source="project_report.txt:r10", content="The target completion date is 2026-04-30."
        )
    ]
    assert ungrounded_specifics(claim, evidence) == ["28 April 2026"]


def test_dates_and_figures_match_across_formats() -> None:
    from app.intelligence.trust.specifics import ungrounded_specifics

    evidence = [
        EvidenceText(source="a.txt:r1", content="Completion is 2026-04-30."),
        EvidenceText(source="budget.csv:r2", content="migration,450000,no"),
    ]
    claim = "Spend of 450,000 was unapproved and completion is 30 April 2026."
    assert ungrounded_specifics(claim, evidence) == []


def test_labels_and_small_counts_are_not_specifics() -> None:
    from app.intelligence.trust.specifics import ungrounded_specifics

    claim = "Milestone M4 in phase 3 of 2 reports, see r10."
    assert ungrounded_specifics(claim, [EvidenceText(source="a.txt:r1", content="x")]) == []


async def test_composite_rule_4_downgrades_a_supported_claim_with_an_ungrounded_date() -> None:
    composite = CompositeVerifier(_Fixed(VerificationStatus.SUPPORTED), LexicalVerifier())
    result = await composite.verify(
        _request(
            "The project report states completion on 28 April 2026.",
            ("project_report.txt", 10, "The target completion date is 2026-04-30."),
        )
    )
    assert result.status is VerificationStatus.PARTIALLY_SUPPORTED
    overstated = [i for i in result.issues if i.issue_type is IssueType.OVERSTATED_CLAIM]
    assert overstated and overstated[0].element == "28 April 2026"
    # Partially supported is actionable: the replanning loop can go and look for it.
    assert result.actionable


async def test_composite_rule_4_leaves_a_grounded_claim_alone() -> None:
    composite = CompositeVerifier(_Fixed(VerificationStatus.SUPPORTED), LexicalVerifier())
    result = await composite.verify(_request(*_RIGHT_DATE))
    assert result.status is VerificationStatus.SUPPORTED


# --- BUG-021: a value in the evidence, in the wrong role ----------------------------------


def test_a_number_where_a_date_belongs_is_named() -> None:
    from app.intelligence.trust.specifics import numbers_as_dates

    assert numbers_as_dates("Shipment 9012 was delivered to XYZ Traders on 9012") == ["9012"]
    assert numbers_as_dates("Invoice dated 4821 was paid") == ["4821"]
    # Real dates, plausible years, and agents are not.
    assert numbers_as_dates("delivered on 20 September by driver Priya Menon") == []
    assert numbers_as_dates("closed on 2026-05-14") == []
    assert numbers_as_dates("budgeted on 2026 figures") == []
    assert numbers_as_dates("Shipment 9012 was delivered by 4821 Logistics") == []


async def test_composite_rule_4_catches_the_shipment_number_read_as_a_date() -> None:
    """BUG-021, verbatim: both verifiers passed it, because 9012 is on the cited line."""
    composite = CompositeVerifier(_Fixed(VerificationStatus.SUPPORTED), LexicalVerifier())
    result = await composite.verify(
        _request(
            "Shipment 9012 was delivered to XYZ Traders on 9012",
            (
                "shipment_delivery_confirmation.txt",
                1,
                "Shipment 9012 was delivered to XYZ Traders on 20 September by driver Priya "
                "Menon. No discrepancies were reported.",
            ),
        )
    )
    assert result.status is VerificationStatus.PARTIALLY_SUPPORTED
    misread = [i for i in result.issues if i.issue_type is IssueType.DATE_AMBIGUITY]
    assert misread and misread[0].element == "9012"
