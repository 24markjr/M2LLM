"""Phase B4: the second reviewer. Only approvals are re-checked; a dissent downgrades one."""

from __future__ import annotations

import pytest

from app.core.config import get_settings
from app.integrations import verification as v
from app.llm.echo import EchoProvider
from app.schemas.verification import (
    IssueType,
    VerificationIssue,
    VerificationRequest,
    VerificationResult,
    VerificationStatus,
)


class _Fixed:
    def __init__(self, status: VerificationStatus, name: str) -> None:
        self.status, self.name, self.calls = status, name, 0

    async def verify(self, request: VerificationRequest) -> VerificationResult:
        self.calls += 1
        issues = (
            []
            if self.status is VerificationStatus.SUPPORTED
            else [VerificationIssue(issue_type=IssueType.EVIDENCE_MISMATCH, description="differs")]
        )
        return VerificationResult(
            status=self.status, confidence=0.9, verifier=self.name, issues=issues
        )


REQUEST = VerificationRequest.model_construct(finding_id="F-001", claim="c", evidence=[])


async def test_an_approval_the_reviewer_confirms_stands_with_both_opinions() -> None:
    council = v.CouncilVerifier(
        _Fixed(VerificationStatus.SUPPORTED, "composite"),
        _Fixed(VerificationStatus.SUPPORTED, "baseline"),
        "llama3.2:3b",
    )
    result = await council.verify(REQUEST)
    assert result.status is VerificationStatus.SUPPORTED
    assert [o.verifier for o in result.opinions] == ["composite", "reviewer:llama3.2:3b"]


async def test_a_dissent_downgrades_the_finding_and_says_why() -> None:
    council = v.CouncilVerifier(
        _Fixed(VerificationStatus.SUPPORTED, "composite"),
        _Fixed(VerificationStatus.CONTRADICTED, "baseline"),
        "llama3.2:3b",
    )
    result = await council.verify(REQUEST)
    assert result.status is VerificationStatus.PARTIALLY_SUPPORTED
    assert result.issues[-1].issue_type is IssueType.REVIEWER_DISSENT


async def test_a_rejection_is_not_sent_to_the_reviewer() -> None:
    reviewer = _Fixed(VerificationStatus.SUPPORTED, "baseline")
    council = v.CouncilVerifier(_Fixed(VerificationStatus.UNSUPPORTED, "composite"), reviewer, "m")
    assert (await council.verify(REQUEST)).status is VerificationStatus.UNSUPPORTED
    assert reviewer.calls == 0


def test_the_council_is_off_unless_a_reviewer_model_is_named(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    assert not isinstance(v.build_verification_provider(EchoProvider()), v.CouncilVerifier)
    monkeypatch.setattr(get_settings(), "reviewer_model", "llama3.2:3b")
    assert isinstance(v.build_verification_provider(EchoProvider()), v.CouncilVerifier)
