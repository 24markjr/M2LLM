"""Demo readiness: date order checked by code, and reference numbers never read as figures."""

from __future__ import annotations

from app.integrations.verification import misordered
from app.intelligence.chronology import check_chronology
from app.intelligence.temporal import find_figures
from app.schemas.finding import Finding
from app.schemas.verification import IssueType, VerificationResult, VerificationStatus

SUPPORTED = VerificationResult(status=VerificationStatus.SUPPORTED, confidence=0.9)


def test_a_false_order_of_two_dates_is_caught() -> None:
    """Measured on the VAJRA case: the model wrote this, and the verifier passed it."""
    check = check_chronology(
        "Payment was released on 25 March 2026, which is after the inspection report of "
        "2 April 2026"
    )
    assert check.checked and not check.holds
    assert "25 March 2026 is before 2 April 2026" in check.reason


def test_a_true_order_holds_and_the_year_carries_over() -> None:
    assert check_chronology("Paid on 25 March 2026, before the report of 2 April").holds
    assert check_chronology("Delivered on 28 March 2026, after the due date of 15 March 2026").holds


def test_what_cannot_be_read_safely_is_left_alone() -> None:
    assert not check_chronology("Paid was not made after 2 April 2026 but on 25 March 2026").checked
    assert not check_chronology("The invoice is dated 20 March 2026.").checked
    assert not check_chronology(
        "Due 15 March 2026, delivered 28 March 2026, paid 25 March 2026"
    ).checked
    assert not check_chronology(
        "Delivered in March 2026, after the order of 10 January 2026"
    ).checked


def test_a_misordered_claim_is_contradicted_whatever_the_verifier_said() -> None:
    finding = Finding(
        finding_id="F-002",
        claim=(
            "Payment was released on 25 March 2026, which is after the inspection of 2 April 2026"
        ),
    )
    result = misordered(finding, SUPPORTED)
    assert result.status is VerificationStatus.CONTRADICTED
    assert [i.issue_type for i in result.issues] == [IssueType.CHRONOLOGY_ERROR]
    right = Finding(
        finding_id="F-003", claim="Paid on 25 March 2026, before the report of 2 April 2026"
    )
    assert misordered(right, SUPPORTED).status is VerificationStatus.SUPPORTED


def test_reference_numbers_are_names_not_figures() -> None:
    """Measured: "014" from VJR/SO/2026/014 was demanded of a ledger line, and a correct
    overpayment finding was discarded."""
    figures = [
        w for w, _ in find_figures("Paid INR 4,20,00,000 against VJR/SO/2026/014, PV-2026-0356")
    ]
    assert figures == ["4,20,00,000"]
    assert [w for w, _ in find_figures("migration,450000,no")] == ["450000"]
    assert [w for w, _ in find_figures("spend 287,500 by 2026-04-30")] == ["287,500"]


def test_a_computed_figure_cites_the_verified_lines_it_comes_from() -> None:
    """Measured: "the overpayment is INR 42,00,000" cited only the INR 3,78,00,000 line."""
    from app.conversation.service import _with_inputs
    from app.conversation.tools import CaseMaterial

    material = CaseMaterial(
        case_id="CASE-2026-00001",
        documents={
            "ledger.xlsx": "head\nhead\nhead\nPV-2026-0356,25 March 2026,Invoice,4,20,00,000",
            "minutes.txt": "a\nPayment approved for 36 units: INR 3,78,00,000",
        },
    )
    claim = "The overpayment against the accepted units is INR 42,00,000"
    assert _with_inputs(claim, ["minutes.txt:r2"], ["ledger.xlsx:r4"], material) == [
        "minutes.txt:r2",
        "ledger.xlsx:r4",
    ]
    # A figure that is no difference or sum of verified figures gains nothing.
    invented = "The overpayment against the accepted units is INR 50,00,000"
    assert _with_inputs(invented, ["minutes.txt:r2"], ["ledger.xlsx:r4"], material) == [
        "minutes.txt:r2"
    ]


def test_followed_and_preceded_read_both_ways() -> None:
    assert not check_chronology(
        "The payment (25 March 2026) followed the inspection (2 April 2026)"
    ).holds
    assert check_chronology(
        "Payment on 25 March 2026 was followed by the inspection on 2 April 2026"
    ).holds
    assert check_chronology(
        "The inspection on 2 April 2026 was preceded by payment on 25 March 2026"
    ).holds
    assert check_chronology(
        "Payment on 25 March 2026 preceded the inspection on 2 April 2026"
    ).holds


def test_a_summary_sentence_with_a_false_order_is_contradicted() -> None:
    """Measured: the written summary repeated the false order as supported."""
    from app.intelligence.synthesis.grounding import check_narrative
    from app.schemas.result import SectionKind
    from app.schemas.trust import EvidenceText, TrustStatus

    evidence = [
        EvidenceText(source="ledger.xlsx:r4", content="PV-2026-0356, 25 March 2026, 4,20,00,000"),
        EvidenceText(source="jir.docx:r3", content="Date of report: 2 April 2026."),
    ]
    check = check_narrative(
        SectionKind.EXECUTIVE_SUMMARY,
        "The payment date (25 March 2026) followed the inspection report date (2 April 2026).",
        evidence,
    )
    assert check is not None
    assert check.sentences[0].status is TrustStatus.CONTRADICTED


def test_a_written_out_calculation_is_computed_not_trusted() -> None:
    """Measured: 'the overpayment is INR 3,78,00,000 (4,20,00,000 - 3,78,00,000)' was verified."""
    from app.intelligence.calculation import check_calculation

    wrong = check_calculation("The overpayment is INR 3,78,00,000 (₹4,20,00,000 - ₹3,78,00,000).")
    assert wrong.checked and not wrong.holds
    assert "is 42,00,000, not 3,78,00,000" in wrong.reason
    right = check_calculation("The overpayment is INR 42,00,000 (₹4,20,00,000 - ₹3,78,00,000).")
    assert right.checked and right.holds
    assert not check_calculation(
        "Voucher PV-2026-0356 dated 2026-03-25 for INR 4,20,00,000"
    ).checked
    finding = Finding(
        finding_id="F-001",
        claim="The overpayment is INR 3,78,00,000 (₹4,20,00,000 - ₹3,78,00,000).",
    )
    result = misordered(finding, SUPPORTED)
    assert result.status is VerificationStatus.CONTRADICTED
    assert [i.issue_type for i in result.issues] == [IssueType.ARITHMETIC_ERROR]
