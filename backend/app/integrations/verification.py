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
from app.intelligence.arithmetic import is_computed, worked_out
from app.intelligence.calculation import check_calculation
from app.intelligence.chronology import check_chronology
from app.intelligence.trust.lexical import verify_claim
from app.intelligence.trust.specifics import numbers_as_dates, ungrounded_specifics
from app.llm.errors import StructuredOutputError
from app.llm.prompts import get_prompt_library
from app.llm.provider import CompletionRequest, CompletionResponse, EmbeddingResponse, LLMProvider
from app.llm.structured import generate_structured
from app.schemas.common import JarvisModel, Severity
from app.schemas.event import EventType
from app.schemas.evidence import is_seen_line
from app.schemas.finding import Finding
from app.schemas.language import is_translated_line
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
                remote: VerificationResult = VerificationResult.model_validate(response.json())
                return remote
        except (httpx.HTTPError, ValueError) as exc:
            reason = f"{type(exc).__name__}: {exc}"
            log.warning("verification_degraded", reason=reason)
            result = await self._fallback.verify(request)
            degraded: VerificationResult = result.model_copy(
                update={"degraded": True, "degraded_reason": reason, "verifier": "baseline"}
            )
            return degraded


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
            # A difference or total worked out from the claim's own figures is on no line, and is
            # not unsupported for that (v4 Phase 2): an overrun of 37,500 from 287,500 and 250,000.
            missing = [m for m in missing if not is_computed(request.claim, m)]
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

        chosen = await _with_entailment(request, chosen, opinions)
        combined: VerificationResult = chosen.model_copy(
            update={"verifier": self.name, "opinions": opinions}
        )
        return combined


# Where the entailment model is trusted (v4 Phase 2): it is strong on a stated status ("was
# approved" against "no budget line covers it") and weak on comparing numbers, so it may only lower
# an approval it confidently contradicts, or decide where the model verifier reached no verdict.
NLI_DECIDES = 0.8


async def _with_entailment(
    request: VerificationRequest, chosen: VerificationResult, opinions: list[VerifierOpinion]
) -> VerificationResult:
    from app.intelligence.trust.nli import entailment

    pool = evidence_pool(request)
    try:
        verdict = await entailment(
            " ".join(f"{e.source}: {e.content}" for e in pool), request.claim
        )
    except Exception as exc:  # noqa: BLE001 - a third opinion never costs the first two
        log.warning("nli_failed", error=f"{type(exc).__name__}: {exc}")
        return chosen
    if verdict is None:
        return chosen
    status = {
        "entailment": VerificationStatus.SUPPORTED,
        "contradiction": VerificationStatus.CONTRADICTED,
    }.get(verdict.label, VerificationStatus.INCONCLUSIVE)
    opinions.append(VerifierOpinion(verifier="nli", status=status))

    # Arithmetic is beyond it: a figure worked out from the evidence reads as a contradiction.
    computed = worked_out(request.claim, [e.content for e in pool])
    if (
        chosen.status is VerificationStatus.SUPPORTED
        and verdict.contradiction >= NLI_DECIDES
        and not computed
    ):
        return chosen.model_copy(
            update={
                "status": VerificationStatus.PARTIALLY_SUPPORTED,
                "issues": [
                    *chosen.issues,
                    VerificationIssue(
                        issue_type=IssueType.EVIDENCE_MISMATCH,
                        description=(
                            "an entailment model reads the cited evidence as contradicting the "
                            f"claim ({verdict.contradiction:.2f})"
                        ),
                    ),
                ],
            }
        )
    # The model verifier reached no verdict (the lexical fallback may have stood in): an entailment
    # model reads meaning, word overlap does not - but a lexical contradiction is never overridden.
    undecided = opinions[0].status is VerificationStatus.INCONCLUSIVE
    if (
        undecided
        and chosen.status is not VerificationStatus.CONTRADICTED
        and (verdict.entailment >= NLI_DECIDES or verdict.contradiction >= NLI_DECIDES)
    ):
        return chosen.model_copy(
            update={
                "status": status,
                "degraded": True,
                "degraded_reason": (
                    "the model verifier reached no verdict; the entailment model's "
                    f"{verdict.label} "
                    f"({max(verdict.entailment, verdict.contradiction):.2f}) was used"
                ),
            }
        )
    return chosen


class _OtherModel:
    """The same provider, every call sent to another model: the second reviewer's voice."""

    def __init__(self, provider: LLMProvider, model: str) -> None:
        self._provider = provider
        self._model = model

    @property
    def model_id(self) -> str:
        return self._model

    async def complete(self, request: CompletionRequest) -> CompletionResponse:
        return await self._provider.complete(request.model_copy(update={"model": self._model}))

    async def embed(self, texts: list[str]) -> EmbeddingResponse:
        return await self._provider.embed(texts)

    async def health(self) -> bool:
        return await self._provider.health()


class CouncilVerifier:
    """A second, independent reviewer for what the verifier approved (Phase B4, llm-council).

    Only SUPPORTED findings are re-checked - the failure that matters is a wrong claim approved, and
    re-checking rejections would double the cost for nothing. The reviewer is another model with the
    same evidence and no reasoning trail. If it does not confirm, the finding is downgraded to
    PARTIALLY_SUPPORTED with a REVIEWER_DISSENT issue, and both opinions are recorded.
    """

    name = "council"

    def __init__(
        self, inner: VerificationProvider, reviewer: VerificationProvider, model: str
    ) -> None:
        self._inner = inner
        self._reviewer = reviewer
        self._model = model

    async def verify(self, request: VerificationRequest) -> VerificationResult:
        first = await self._inner.verify(request)
        if first.status is not VerificationStatus.SUPPORTED:
            return first
        second = await self._reviewer.verify(request)
        opinions = [
            *(first.opinions or [VerifierOpinion(verifier=first.verifier, status=first.status)]),
            VerifierOpinion(verifier=f"reviewer:{self._model}", status=second.status),
        ]
        if second.status is VerificationStatus.SUPPORTED:
            return first.model_copy(update={"opinions": opinions})
        dissent = VerificationIssue(
            issue_type=IssueType.REVIEWER_DISSENT,
            description=(
                f"the second reviewer ({self._model}) found it {second.status.value.lower()}"
            ),
        )
        return first.model_copy(
            update={
                "status": VerificationStatus.PARTIALLY_SUPPORTED,
                "issues": [*first.issues, dissent],
                "opinions": opinions,
            }
        )


def build_verification_provider(llm: LLMProvider) -> VerificationProvider:
    """The configured verifier, with the second reviewer around it when one is configured."""
    chosen = _configured_verifier(llm)
    model = get_settings().reviewer_model
    if not model:
        return chosen
    return CouncilVerifier(chosen, BaselineVerifier(_OtherModel(llm, model)), model)


def _configured_verifier(llm: LLMProvider) -> VerificationProvider:
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


def described_only(
    finding: Finding, evidence_text: dict[str, str], result: VerificationResult
) -> VerificationResult:
    """A finding resting only on what a vision model saw is not fully supported (Phase 39).

    Applied after whichever verifier ran. Text read from a document, a scan or a recording is
    evidence; a vision model's description of an image (`[seen]` lines) is a model's account and can
    be wrong. A claim whose every resolved citation is such a line keeps the verifier's reasoning,
    but `SUPPORTED` becomes `PARTIALLY_SUPPORTED` with an issue saying why - actionable, so the loop
    can look for text that confirms it.
    """
    if result.status is not VerificationStatus.SUPPORTED:
        return result
    cited = [evidence_text.get(ref.as_ref(), "") for ref in finding.evidence if ref.is_resolved]
    if not cited or not all(is_seen_line(text) for text in cited):
        return result
    described: VerificationResult = result.model_copy(
        update={
            "status": VerificationStatus.PARTIALLY_SUPPORTED,
            "issues": [
                *result.issues,
                VerificationIssue(
                    issue_type=IssueType.DESCRIBED_ONLY,
                    description=(
                        "every cited line is a vision model's description of an image, not text "
                        "read from a source; it needs confirming by something read"
                    ),
                ),
            ],
        }
    )
    return described


def translated_only(
    finding: Finding, evidence_text: dict[str, str], result: VerificationResult
) -> VerificationResult:
    """A finding resting only on machine translation needs review; never auto-verified (v4 Phase 6).

    Each line of a document in an Indian language is read through its English translation, marked
    `[translated:<code>]`. When every resolved citation is such a line, nothing the claim rests on
    is the source's own words: `SUPPORTED` becomes `PARTIALLY_SUPPORTED`, with an issue telling a
    person to check the translation against the original. A finding that also cites an original
    line - a Hindi report against an English ledger - is verified as usual.
    """
    if result.status is not VerificationStatus.SUPPORTED:
        return result
    cited = [evidence_text.get(ref.as_ref(), "") for ref in finding.evidence if ref.is_resolved]
    if not cited or not all(is_translated_line(text) for text in cited):
        return result
    return result.model_copy(
        update={
            "status": VerificationStatus.PARTIALLY_SUPPORTED,
            "issues": [
                *result.issues,
                VerificationIssue(
                    issue_type=IssueType.TRANSLATED_ONLY,
                    description=(
                        "every cited line is a machine translation; confirm it against the "
                        "original text before relying on it"
                    ),
                ),
            ],
        }
    )


def misordered(finding: Finding, result: VerificationResult) -> VerificationResult:
    """A claim whose dates are not in the order it states is wrong, whatever else it cites.

    Checked by code (`intelligence/chronology.py`), after whichever verifier ran: both dates can
    be on the cited lines while "25 March is after 2 April" is false. Such a claim becomes
    `CONTRADICTED`, with the computed order as the issue.
    """
    check = check_chronology(finding.claim)
    if not check.checked or check.holds:
        # And a calculation written out in the claim (`intelligence/calculation.py`): measured,
        # "the overpayment is INR 3,78,00,000 (4,20,00,000 - 3,78,00,000)" was passed.
        sums = check_calculation(finding.claim)
        if not sums.checked or sums.holds:
            return result
        return result.model_copy(
            update={
                "status": VerificationStatus.CONTRADICTED,
                "issues": [
                    *result.issues,
                    VerificationIssue(
                        issue_type=IssueType.ARITHMETIC_ERROR,
                        description=sums.reason,
                        severity=Severity.HIGH,
                    ),
                ],
            }
        )
    return result.model_copy(
        update={
            "status": VerificationStatus.CONTRADICTED,
            "issues": [
                *result.issues,
                VerificationIssue(
                    issue_type=IssueType.CHRONOLOGY_ERROR,
                    description=check.reason,
                    severity=Severity.HIGH,
                ),
            ],
        }
    )


async def verify_finding(
    provider: VerificationProvider,
    finding: Finding,
    evidence_text: dict[str, str],
    *,
    emit: object | None = None,
) -> VerificationResult:
    """Verify one finding and attach the result to it."""
    result = misordered(
        finding,
        translated_only(
            finding,
            evidence_text,
            described_only(
                finding,
                evidence_text,
                await provider.verify(build_request(finding, evidence_text)),
            ),
        ),
    )
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
