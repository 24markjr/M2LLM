"""Independent verification of a claim against its evidence.

The defining property is what a verification request does *not* contain: the reasoning that
produced the claim. A verifier shown the argument tends to be persuaded by it. Shown only the
claim and the evidence text, it can actually disagree — which is the only way verification is
worth running at all.

Member 4 owns the production verifier (Phase 15). Member 1 owns this contract and a baseline
implementation, so the verification story holds whether or not the remote service arrives.
"""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum

from pydantic import Field, model_validator

from app.schemas.common import (
    JarvisModel,
    NonEmptyStr,
    Severity,
    UnitFloat,
    utcnow,
)
from app.schemas.evidence import EvidenceRef


class VerificationStatus(StrEnum):
    SUPPORTED = "SUPPORTED"
    PARTIALLY_SUPPORTED = "PARTIALLY_SUPPORTED"
    UNSUPPORTED = "UNSUPPORTED"
    # The evidence says the opposite. Distinct from UNSUPPORTED, and far more interesting:
    # an unsupported claim is unproven, a contradicted one is wrong.
    CONTRADICTED = "CONTRADICTED"
    # The check could not be performed. Never treated as a pass.
    INCONCLUSIVE = "INCONCLUSIVE"


class IssueType(StrEnum):
    NO_EVIDENCE = "NO_EVIDENCE"
    UNRESOLVED_CITATION = "UNRESOLVED_CITATION"
    EVIDENCE_MISMATCH = "EVIDENCE_MISMATCH"
    OVERSTATED_CLAIM = "OVERSTATED_CLAIM"
    SOURCE_CONFLICT = "SOURCE_CONFLICT"
    UNIT_MISMATCH = "UNIT_MISMATCH"
    DATE_AMBIGUITY = "DATE_AMBIGUITY"
    ARITHMETIC_ERROR = "ARITHMETIC_ERROR"


class VerificationIssue(JarvisModel):
    """One specific problem found with a claim.

    Issues are the verifier's actual output. A bare status tells the replanning loop nothing
    it can act on; `element` plus `issue_type` tells it exactly what to go and fix.
    """

    issue_type: IssueType
    description: NonEmptyStr
    severity: Severity = Severity.MEDIUM
    # Which part of the claim is at fault, when it can be localised.
    element: str = ""


class VerificationRequest(JarvisModel):
    """What the verifier is given — deliberately no more than this.

    There is no field here for the reasoning trail, the observations, or the plan. That is
    not an oversight; it is the contract. See the module docstring.
    """

    claim: NonEmptyStr
    evidence: list[EvidenceRef] = Field(default_factory=list)
    # Evidence text, keyed by evidence id, so the verifier reads content rather than
    # trusting a pointer.
    evidence_content: dict[str, str] = Field(default_factory=dict)
    # Neutral hints only: units, date formats, currency. Never conclusions.
    context_hints: dict[str, str] = Field(default_factory=dict)


class VerificationResult(JarvisModel):
    """The verifier's verdict."""

    status: VerificationStatus
    confidence: UnitFloat
    issues: list[VerificationIssue] = Field(default_factory=list)
    # Which implementation produced this: "baseline" or a remote service identifier.
    # Reports state it, because a degraded verification is not the same as a full one.
    verifier: str = "baseline"
    # True when the remote verifier was unavailable and baseline was used instead.
    # Verification is never silently skipped.
    degraded: bool = False
    degraded_reason: str = ""
    verified_at: datetime = Field(default_factory=utcnow)

    @model_validator(mode="after")
    def _failures_must_be_explained(self) -> VerificationResult:
        failing = {
            VerificationStatus.UNSUPPORTED,
            VerificationStatus.CONTRADICTED,
            VerificationStatus.PARTIALLY_SUPPORTED,
        }
        if self.status in failing and not self.issues:
            raise ValueError(
                f"status={self.status.value} requires at least one issue: a rejection "
                "without a stated reason cannot be acted on by the replanning loop"
            )
        if self.degraded and not self.degraded_reason.strip():
            raise ValueError("degraded=True requires degraded_reason")
        return self

    @property
    def passed(self) -> bool:
        return self.status is VerificationStatus.SUPPORTED

    @property
    def actionable(self) -> bool:
        """Whether replanning could plausibly improve this.

        A contradicted claim is not a gap to fill — more evidence will not rescue a claim the
        sources refute. It should be rejected and reported as rejected.
        """
        return self.status in {
            VerificationStatus.PARTIALLY_SUPPORTED,
            VerificationStatus.UNSUPPORTED,
            VerificationStatus.INCONCLUSIVE,
        }
