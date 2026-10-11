"""Phase 48: challenge a finding - counter-evidence, its own lines, the verifier, authority.

A challenge looks for what would make a finding wrong. Counter-evidence from a stronger source can
overturn it; from an equal or weaker one, or a claim its own line does not hold, contests it. The
stored finding is never changed: before and after are kept side by side.
"""

from __future__ import annotations

from collections.abc import Iterator

import pytest
from httpx import ASGITransport, AsyncClient

from app.api.app import create_app
from app.api.registry import MissionRecord, get_registry
from app.api.v1 import missions as mission_routes
from app.evaluation.challenge import CORPUS, run_challenge_benchmark
from app.intelligence.challenge import (
    ChallengeOutcome,
    challenge,
    disagreement,
    find_counter_evidence,
)
from app.intelligence.confidence import rescore
from app.intelligence.reasoning.statements import type_statements
from app.orchestration.mission import MissionResult, MissionStatus, Stage
from app.schemas.common import SourceLocator, new_run_id
from app.schemas.evidence import ClaimElement, EvidenceRef, ResolutionStatus
from app.schemas.finding import Finding
from app.schemas.objective import Objective
from app.schemas.verification import (
    IssueType,
    VerificationIssue,
    VerificationRequest,
    VerificationResult,
    VerificationStatus,
)

TEXT = {
    f"{name}:r{n}": line
    for name, text in CORPUS.items()
    for n, line in enumerate(text.splitlines(), start=1)
}


def _finding(claim: str, cite: str) -> Finding:
    document, row = cite.rsplit(":r", 1)
    finding = Finding(
        finding_id="F-001",
        claim=claim,
        evidence=[
            EvidenceRef(
                evidence_id="E-001",
                locator=SourceLocator(document_id=document, document_name=document, row=int(row)),
                resolution=ResolutionStatus.RESOLVED,
            )
        ],
        elements=[ClaimElement(text=claim, supported=True)],
        verification=VerificationResult(status=VerificationStatus.SUPPORTED, confidence=0.9),
    )
    finding.classification = finding.classify()
    type_statements([finding], comparative=False)
    rescore([finding], evidence_text=TEXT)
    return finding


# --- the disagreement rule ------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("claim", "line", "reason"),
    [
        (
            "Go-live is 26 June 2026.",
            "Go-live is 12 June 2026.",
            "gives 12 June 2026 where the claim gives 26 June 2026",
        ),
        (
            "The budget is 520,000.",
            "The budget is 480,000.",
            "gives 480,000 where the claim gives 520,000",
        ),
        (
            "Phase 2 continues.",
            "Phase 2 was cancelled.",
            'says "cancelled" where the claim does not',
        ),
        ("Go-live is 12 June 2026.", "Go-live remains 12 June 2026.", ""),
        ("The vendor is Orion Freight.", "The vendor is Kestrel Systems.", ""),
    ],
)
def test_what_counts_as_disagreement(claim: str, line: str, reason: str) -> None:
    assert disagreement(claim, line) == reason


def test_the_cited_line_is_never_its_own_counter_evidence() -> None:
    finding = _finding("Atlas spend to date is 250,000.", "atlas_status_report.txt:r3")
    assert find_counter_evidence(finding, CORPUS) == []


def test_lines_about_something_else_are_not_counter_evidence() -> None:
    """The invoice's 95,000 and the budget's 480,000 are figures, but not about the go-live."""
    finding = _finding("The Atlas go-live date is 26 June 2026.", "atlas_vendor_email.txt:r2")
    locators = [c.locator for c in find_counter_evidence(finding, CORPUS)]
    assert locators == ["atlas_approved_plan.txt:r2", "atlas_status_report.txt:r2"]


# --- outcomes -------------------------------------------------------------------------------------


async def test_a_stronger_source_overturns_and_the_number_falls_to_the_cap() -> None:
    finding = _finding("The Atlas go-live date is 26 June 2026.", "atlas_vendor_email.txt:r2")
    before = finding.confidence.value
    result = await challenge(finding, CORPUS, evidence_text=TEXT, actor="analyst-7")
    assert result.outcome is ChallengeOutcome.OVERTURNED
    assert result.confidence_before == before and result.confidence_after == pytest.approx(0.1)
    assert result.counter_evidence[0].stronger
    assert result.challenged_by == "analyst-7"
    assert finding.confidence.value == before, "the stored finding is not changed"


async def test_a_weaker_source_only_contests() -> None:
    finding = _finding("The Atlas go-live date is 12 June 2026.", "atlas_approved_plan.txt:r2")
    result = await challenge(finding, CORPUS, evidence_text=TEXT)
    assert result.outcome is ChallengeOutcome.CONTESTED
    assert result.confidence_after == pytest.approx(result.confidence_before - 0.15)
    assert "Correspondence" in result.summary


async def test_a_claim_its_own_line_does_not_hold_is_contested_by_itself() -> None:
    finding = _finding("Atlas spend to date is 250,000.", "atlas_status_report.txt:r3")
    result = await challenge(finding, CORPUS, evidence_text=TEXT)
    assert result.outcome is ChallengeOutcome.CONTESTED
    assert result.summary.startswith("Contested by its own citation")


async def test_nothing_against_it_withstands_unchanged() -> None:
    finding = _finding("Atlas spend to date is 210,000.", "atlas_status_report.txt:r3")
    result = await challenge(finding, CORPUS, evidence_text=TEXT)
    assert result.outcome is ChallengeOutcome.WITHSTOOD
    assert result.confidence_after == result.confidence_before


async def test_a_verifier_that_finds_the_counter_lines_consistent_dismisses_them() -> None:
    seen: list[VerificationRequest] = []

    async def consistent(request: VerificationRequest) -> VerificationResult:
        seen.append(request)
        return VerificationResult(status=VerificationStatus.SUPPORTED, confidence=0.9, verifier="m")

    finding = _finding("The Atlas go-live date is 26 June 2026.", "atlas_vendor_email.txt:r2")
    result = await challenge(finding, CORPUS, evidence_text=TEXT, verifier=consistent)
    assert result.outcome is ChallengeOutcome.WITHSTOOD
    assert "SUPPORTED (m)" in result.negation_check
    [request] = seen
    assert set(request.evidence_content) == {
        "atlas_approved_plan.txt:r2",
        "atlas_status_report.txt:r2",
    }, "checked against the counter lines alone"


# --- the benchmark --------------------------------------------------------------------------------


async def test_the_benchmark_catches_five_of_six_and_overturns_no_true_finding() -> None:
    report = await run_challenge_benchmark()
    assert report.challenge_catch_rate == pytest.approx(5 / 6)
    assert report.challenge_false_alarm_rate == 0.0
    missed = [r.case_id for r in report.results if not r.true and not r.caught]
    assert missed == ["false-vendor-name"], "the documented miss, and only it"


# --- the API --------------------------------------------------------------------------------------


@pytest.fixture
def contradicting(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    class _Verifier:
        async def verify(self, request: VerificationRequest) -> VerificationResult:
            return VerificationResult(
                status=VerificationStatus.CONTRADICTED,
                confidence=0.9,
                verifier="test",
                issues=[
                    VerificationIssue(issue_type=IssueType.SOURCE_CONFLICT, description="dates")
                ],
            )

    monkeypatch.setattr(mission_routes, "build_verification_provider", lambda _llm: _Verifier())
    yield


async def test_a_challenge_is_recorded_beside_the_finding(contradicting: None) -> None:
    finding = _finding("The Atlas go-live date is 26 June 2026.", "atlas_vendor_email.txt:r2")
    record = MissionRecord(new_run_id(), Objective(text="When is go-live?"), sorted(CORPUS))
    record.status = MissionStatus.COMPLETED
    record.stage = Stage.DONE
    record.texts = dict(CORPUS)
    record.result = MissionResult(
        run_id=record.run_id,
        objective=record.objective,
        status=MissionStatus.COMPLETED,
        findings=[finding],
        evidence_text=TEXT,
    )
    get_registry()._missions[record.run_id] = record

    async with AsyncClient(transport=ASGITransport(app=create_app()), base_url="http://test") as c:
        response = await c.post(
            f"/api/v1/missions/{record.run_id}/findings/F-001/challenge",
            headers={"X-Jarvis-User": "reviewer-2"},
        )
        listed = (await c.get(f"/api/v1/missions/{record.run_id}/challenges")).json()
        missing = await c.post(f"/api/v1/missions/{record.run_id}/findings/F-404/challenge")

    assert response.status_code == 200
    body = response.json()
    assert body["outcome"] == "OVERTURNED" and body["challenged_by"] == "reviewer-2"
    assert "CONTRADICTED (test)" in body["negation_check"]
    assert [c["finding_id"] for c in listed] == ["F-001"]
    assert missing.status_code == 404
