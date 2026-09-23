"""The verification seam.

Member 4 owns the production verifier. Member 1 owns this contract and a working baseline,
so the verification story holds whether or not the remote service arrives.

**The defining property is what a verifier does not see.** `VerificationRequest` carries a
claim and its evidence and nothing else — no reasoning trail, no observations, no plan. A
verifier shown the argument tends to be persuaded by it, and a verifier that agrees with the
reasoning it was meant to check is worse than no verifier at all: it produces findings that
look checked and are not.

Two things are decided without a model, because they are structural rather than matters of
judgement: a claim with no resolved evidence is `UNSUPPORTED`, and a claim whose evidence is
empty text is `INCONCLUSIVE`. Spending a model call to discover that nothing was cited would
be theatre.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

import httpx
from pydantic import Field

from app.core.config import VerificationProviderName, get_settings
from app.core.logging import get_logger
from app.llm.errors import StructuredOutputError
from app.llm.prompts import get_prompt_library
from app.llm.provider import LLMProvider
from app.llm.structured import generate_structured
from app.schemas.common import JarvisModel, Severity
from app.schemas.event import EventType
from app.schemas.finding import Finding
from app.schemas.verification import (
    IssueType,
    VerificationIssue,
    VerificationRequest,
    VerificationResult,
    VerificationStatus,
)

log = get_logger(__name__)


class VerdictIssue(JarvisModel):
    """An issue as the model reports it, before mapping onto the closed vocabulary."""

    issue_type: str = "EVIDENCE_MISMATCH"
    description: str = ""
    element: str = ""


class VerificationVerdict(JarvisModel):
    """What the model returns. Confidence is advisory and is not used as-is."""

    status: str = "INCONCLUSIVE"
    issues: list[VerdictIssue] = Field(default_factory=list)
    confidence: float | None = Field(default=None, exclude=True)


@runtime_checkable
class VerificationProvider(Protocol):
    async def verify(self, request: VerificationRequest) -> VerificationResult: ...


def build_request(finding: Finding, evidence_text: dict[str, str]) -> VerificationRequest:
    """Assemble what the verifier is allowed to see.

    Note what is absent: the finding's classification, its computed confidence, the
    reasoning that produced it, and the observations it came from. None of them have a
    parameter here, and that is the contract rather than an oversight.
    """
    return VerificationRequest(
        claim=finding.claim,
        evidence=list(finding.evidence),
        evidence_content={
            ref.as_ref(): evidence_text.get(ref.as_ref(), "")
            for ref in finding.evidence
            if ref.is_resolved
        },
    )


def _map_status(raw: str) -> VerificationStatus:
    try:
        return VerificationStatus(raw.strip().upper().replace(" ", "_"))
    except ValueError:
        # An unrecognised verdict is inconclusive, never a pass. Defaulting to SUPPORTED
        # would turn a parsing failure into a verified finding.
        return VerificationStatus.INCONCLUSIVE


def _map_issue(issue: VerdictIssue) -> VerificationIssue:
    try:
        issue_type = IssueType(issue.issue_type.strip().upper().replace(" ", "_"))
    except ValueError:
        issue_type = IssueType.EVIDENCE_MISMATCH
    return VerificationIssue(
        issue_type=issue_type,
        description=issue.description.strip() or "the verifier reported a problem",
        element=issue.element.strip(),
        severity=Severity.MEDIUM,
    )


class BaselineVerifier:
    """Member 1's own independent check. Always available.

    Not a stub: it re-reads the claim against the evidence text with no access to the
    reasoning that produced it. If Member 4's service never arrives, the verification story
    still holds.
    """

    name = "baseline"

    def __init__(self, provider: LLMProvider) -> None:
        self._provider = provider
        self._prompts = get_prompt_library()

    async def verify(self, request: VerificationRequest) -> VerificationResult:
        resolved = [r for r in request.evidence if r.is_resolved]

        if not resolved:
            return VerificationResult(
                status=VerificationStatus.UNSUPPORTED,
                confidence=1.0,
                verifier=self.name,
                issues=[
                    VerificationIssue(
                        issue_type=IssueType.NO_EVIDENCE,
                        description="the claim cites no evidence that could be resolved",
                        severity=Severity.HIGH,
                    )
                ],
            )

        evidence_text = "\n".join(
            f"[{ref}] {text}" for ref, text in request.evidence_content.items() if text.strip()
        )
        if not evidence_text.strip():
            return VerificationResult(
                status=VerificationStatus.INCONCLUSIVE,
                confidence=0.0,
                verifier=self.name,
                issues=[
                    VerificationIssue(
                        issue_type=IssueType.NO_EVIDENCE,
                        description="the cited sources resolved but carry no readable content",
                        severity=Severity.HIGH,
                    )
                ],
            )

        prompt = self._prompts.get("verification").render(
            claim=request.claim, evidence=evidence_text
        )

        try:
            verdict = await generate_structured(
                self._provider, VerificationVerdict, prompt, role="verification"
            )
        except StructuredOutputError:
            # An unverifiable finding stays unverified. Passing it would be the failure.
            log.warning("verification_structured_output_failed")
            return VerificationResult(
                status=VerificationStatus.INCONCLUSIVE,
                confidence=0.0,
                verifier=self.name,
                issues=[
                    VerificationIssue(
                        issue_type=IssueType.EVIDENCE_MISMATCH,
                        description="the verifier could not produce a usable verdict",
                    )
                ],
            )

        status = _map_status(verdict.status)
        issues = [_map_issue(i) for i in verdict.issues]

        # A failing status with no stated reason cannot be acted on by the replanning loop,
        # and the schema refuses to construct one. Supply a generic issue rather than crash.
        failing = {
            VerificationStatus.UNSUPPORTED,
            VerificationStatus.CONTRADICTED,
            VerificationStatus.PARTIALLY_SUPPORTED,
        }
        if status in failing and not issues:
            issues = [
                VerificationIssue(
                    issue_type=IssueType.EVIDENCE_MISMATCH,
                    description="the verifier rejected the claim without naming a reason",
                )
            ]

        # Confidence in the verdict itself, derived from how much evidence backed it.
        # The model's own number is discarded: it is the thing being checked.
        documents = {r.locator.document_id for r in resolved}
        confidence = min(1.0, 0.6 + 0.2 * len(documents))

        return VerificationResult(
            status=status, confidence=confidence, issues=issues, verifier=self.name
        )


class RemoteVerifier:
    """Adapter for Member 4's service, degrading to baseline when it is unavailable.

    Degradation is never silent. A finding verified by a fallback is not the same as one
    verified by the service, and the result says which.
    """

    name = "remote"

    def __init__(self, base_url: str, fallback: BaselineVerifier, timeout_s: float = 30.0) -> None:
        self._base_url = base_url.rstrip("/")
        self._fallback = fallback
        self._timeout_s = timeout_s

    async def verify(self, request: VerificationRequest) -> VerificationResult:
        try:
            async with httpx.AsyncClient(timeout=self._timeout_s) as client:
                response = await client.post(
                    f"{self._base_url}/verify", json=request.model_dump(mode="json")
                )
                response.raise_for_status()
                return VerificationResult.model_validate(response.json())
        except (httpx.HTTPError, ValueError) as exc:
            reason = f"{type(exc).__name__}: {exc}"
            log.warning("verification_degraded", reason=reason)
            result = await self._fallback.verify(request)
            return result.model_copy(
                update={"degraded": True, "degraded_reason": reason, "verifier": "baseline"}
            )


def build_verification_provider(llm: LLMProvider) -> VerificationProvider:
    """The configured verifier."""
    settings = get_settings()
    baseline = BaselineVerifier(llm)

    if settings.verification_provider is VerificationProviderName.REMOTE:
        if settings.verification_base_url:
            return RemoteVerifier(
                settings.verification_base_url, baseline, settings.integration_timeout_s
            )
        log.warning(
            "verification_provider_remote_unconfigured",
            reason="VERIFICATION_BASE_URL is empty; using the baseline verifier",
        )
    return baseline


async def verify_finding(
    provider: VerificationProvider,
    finding: Finding,
    evidence_text: dict[str, str],
    *,
    emit: object | None = None,
) -> VerificationResult:
    """Verify one finding and attach the result to it."""
    result = await provider.verify(build_request(finding, evidence_text))
    finding.verification = result

    if emit is not None:
        emitter = getattr(emit, "emit", None)
        if emitter is not None:
            event = EventType.FINDING_VERIFIED if result.passed else EventType.FINDING_REJECTED
            await emitter(
                event,
                payload={
                    "status": result.status.value,
                    "verifier": result.verifier,
                    "degraded": result.degraded,
                    "issues": [i.issue_type.value for i in result.issues],
                },
                finding_id=finding.finding_id,
            )
            if result.degraded:
                await emitter(
                    EventType.VERIFICATION_DEGRADED,
                    payload={"reason": result.degraded_reason},
                    finding_id=finding.finding_id,
                )

    return result
