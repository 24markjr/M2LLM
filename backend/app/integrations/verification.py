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

from app.core.agent_config import get_lexical_thresholds
from app.core.config import VerificationProviderName, get_settings
from app.core.logging import get_logger
from app.intelligence.trust.lexical import verify_claim
from app.intelligence.trust.specifics import numbers_as_dates, ungrounded_specifics
from app.llm.errors import StructuredOutputError
from app.llm.prompts import get_prompt_library
from app.llm.provider import LLMProvider
from app.llm.structured import generate_structured
from app.schemas.common import JarvisModel, Severity
from app.schemas.event import EventType
from app.schemas.finding import Finding
from app.schemas.trust import EvidenceText, LexicalThresholds, LexicalVerdict, TrustStatus
from app.schemas.verification import (
    IssueType,
    VerificationIssue,
    VerificationRequest,
    VerificationResult,
    VerificationStatus,
    VerifierOpinion,
)
from app.security.injection import wrap_untrusted

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

        readable = {item.source: item.content for item in evidence_pool(request)}
        # Each cited text in its own <document> block, so the prompt marks it as data and a
        # document cannot close its block from inside (Phase 27, Member 4's wrap_untrusted).
        evidence_text = "\n\n".join(wrap_untrusted(ref, text) for ref, text in readable.items())
        if not readable:
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


class LexicalVerifier:
    """Member 4's verifier as a `VerificationProvider` (Phase 26).

    The decision itself is `app/intelligence/trust/lexical.py`, ported from Member 4's
    `trust/verifier.py`: TF-IDF relevance, and a contradiction only when claim and evidence share
    an identifying number and disagree on a date or time. This class is the adapter, and the only
    place Member 4's status vocabulary meets JARVIS's:

    | Member 4 | JARVIS | issue |
    |---|---|---|
    | SUPPORTED | SUPPORTED | - |
    | CONTRADICTED | CONTRADICTED | SOURCE_CONFLICT, naming the source and the reason |
    | UNSUPPORTED | UNSUPPORTED | EVIDENCE_MISMATCH |
    | INSUFFICIENT_EVIDENCE | INCONCLUSIVE | NO_EVIDENCE - never a pass |

    Same independence as the baseline: it sees the claim and the cited text, nothing else.
    """

    name = "lexical"

    def __init__(self, thresholds: LexicalThresholds | None = None) -> None:
        self._thresholds = thresholds or get_lexical_thresholds()

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

        pool = evidence_pool(request)
        if not pool:
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

        verdict = verify_claim(request.claim, pool, self._thresholds)
        return lexical_result(verdict, documents={r.locator.document_id for r in resolved})


def evidence_pool(request: VerificationRequest) -> list[EvidenceText]:
    """The readable evidence text of a request, one item per cited locator."""
    return [
        EvidenceText(source=ref, content=_without_ref(ref, text))
        for ref, text in request.evidence_content.items()
        if _without_ref(ref, text).strip()
    ]


def _without_ref(ref: str, text: str) -> str:
    """Evidence text arrives as "doc.txt:r10: <line>". The locator is not evidence.

    Left in, the document name and `r10` would count as matching terms in the TF-IDF score
    against any claim that names the document.
    """
    prefix = f"{ref}: "
    return text[len(prefix) :] if text.startswith(prefix) else text


def lexical_result(verdict: LexicalVerdict, *, documents: set[str]) -> VerificationResult:
    """Map Member 4's verdict onto JARVIS's, attaching the issue the replanning loop acts on."""
    # Confidence in the verdict, derived as the baseline derives it: from how many distinct
    # documents backed it. The TF-IDF score is not used. It is a similarity, not a calibrated
    # probability, and confidence in this project is computed, never asserted.
    confidence = min(1.0, 0.6 + 0.2 * len(documents))

    if verdict.status is TrustStatus.SUPPORTED:
        return VerificationResult(
            status=VerificationStatus.SUPPORTED, confidence=confidence, verifier="lexical"
        )
    if verdict.status is TrustStatus.CONTRADICTED:
        return VerificationResult(
            status=VerificationStatus.CONTRADICTED,
            confidence=confidence,
            verifier="lexical",
            issues=[
                VerificationIssue(
                    issue_type=IssueType.SOURCE_CONFLICT,
                    description=verdict.reasoning,
                    severity=Severity.HIGH,
                    element=", ".join(verdict.contradicting),
                )
            ],
        )
    if verdict.status is TrustStatus.UNSUPPORTED:
        return VerificationResult(
            status=VerificationStatus.UNSUPPORTED,
            confidence=confidence,
            verifier="lexical",
            issues=[
                VerificationIssue(
                    issue_type=IssueType.EVIDENCE_MISMATCH,
                    description=verdict.reasoning,
                )
            ],
        )
    # INSUFFICIENT_EVIDENCE, and PARTIALLY_SUPPORTED which a single claim never receives.
    return VerificationResult(
        status=VerificationStatus.INCONCLUSIVE,
        confidence=0.0,
        verifier="lexical",
        issues=[
            VerificationIssue(
                issue_type=IssueType.NO_EVIDENCE,
                description=verdict.reasoning,
                severity=Severity.HIGH,
            )
        ],
    )


class CompositeVerifier:
    """A model verifier and the lexical verifier, each doing what it is good at (Phase 26).

    The lexical check is precise on one thing: a shared identifier with a different date or time
    is a contradiction, and it does not need to understand a sentence to see it. The model reads
    meaning. Neither alone is enough, and averaging them would be worse than either.

    Resolution, in order:

    1. Lexical says CONTRADICTED and the model does not: **CONTRADICTED**. The rule needs a
       shared identifier, disjoint dates or times, and relevance >= 0.5.
    2. The model could not reach a verdict (INCONCLUSIVE) and lexical can: the lexical verdict,
       marked **degraded** with the reason. A weaker check that is used is never a silent one.
    3. Otherwise the model's verdict. A lexical SUPPORTED never overrides a model rejection:
       word overlap is not meaning.
    4. Whatever the verdict, a SUPPORTED one becomes **PARTIALLY_SUPPORTED** when the claim
       states a date or figure that none of its cited evidence contains (A15, BUG-018). The
       issue names the value, which gives the replanning loop something specific to look for.

    Both opinions are recorded on the result, so how often they disagree can be measured.
    """

    name = "composite"

    def __init__(self, primary: VerificationProvider, lexical: LexicalVerifier) -> None:
        self._primary = primary
        self._lexical = lexical

    async def verify(self, request: VerificationRequest) -> VerificationResult:
        model = await self._primary.verify(request)
        lexical = await self._lexical.verify(request)
        opinions = [
            VerifierOpinion(verifier=model.verifier, status=model.status),
            VerifierOpinion(verifier=lexical.verifier, status=lexical.status),
        ]

        if (
            lexical.status is VerificationStatus.CONTRADICTED
            and model.status is not VerificationStatus.CONTRADICTED
        ):
            chosen = lexical.model_copy(update={"issues": [*lexical.issues, *model.issues]})
        elif model.status is VerificationStatus.INCONCLUSIVE and lexical.status in {
            VerificationStatus.SUPPORTED,
            VerificationStatus.UNSUPPORTED,
        }:
            chosen = lexical.model_copy(
                update={
                    "degraded": True,
                    "degraded_reason": (
                        f"the {model.verifier} verifier reached no verdict; "
                        "the lexical verdict was used"
                    ),
                }
            )
        else:
            chosen = model

        if chosen.status is VerificationStatus.SUPPORTED:
            issues: list[VerificationIssue] = []
            missing = ungrounded_specifics(request.claim, evidence_pool(request))
            if missing:
                issues.append(
                    VerificationIssue(
                        issue_type=IssueType.OVERSTATED_CLAIM,
                        description=(
                            "the claim states "
                            + ", ".join(missing)
                            + ", which none of its cited evidence contains"
                        ),
                        element=", ".join(missing),
                    )
                )
            # BUG-021: a value can be in the evidence and still be in the wrong role.
            misread = numbers_as_dates(request.claim)
            if misread:
                issues.append(
                    VerificationIssue(
                        issue_type=IssueType.DATE_AMBIGUITY,
                        description=(
                            "the claim gives "
                            + ", ".join(misread)
                            + " as a date, and a bare number of that size is not one"
                        ),
                        element=", ".join(misread),
                    )
                )
            if issues:
                chosen = chosen.model_copy(
                    update={
                        "status": VerificationStatus.PARTIALLY_SUPPORTED,
                        "issues": [*chosen.issues, *issues],
                    }
                )

        return chosen.model_copy(update={"verifier": self.name, "opinions": opinions})


def build_verification_provider(llm: LLMProvider) -> VerificationProvider:
    """The configured verifier."""
    settings = get_settings()
    baseline = BaselineVerifier(llm)

    if settings.verification_provider is VerificationProviderName.LEXICAL:
        return LexicalVerifier()
    if settings.verification_provider is VerificationProviderName.COMPOSITE:
        return CompositeVerifier(baseline, LexicalVerifier())

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
                    # Every verifier consulted, so composite disagreement is measurable.
                    "opinions": {o.verifier: o.status.value for o in result.opinions},
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
