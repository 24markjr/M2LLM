"""Phase 15 — independent verification.

The most important test asserts an absence: `VerificationRequest` has no field for the
reasoning that produced the claim. A verifier shown the argument tends to agree with it, and
a verifier that agrees is worse than none — it produces findings that look checked.
"""

from __future__ import annotations

import json

import pytest

from app.core.events import EventBus, MemoryEventSink, RunEventEmitter
from app.integrations.verification import (
    BaselineVerifier,
    RemoteVerifier,
    VerificationProvider,
    build_request,
    build_verification_provider,
    verify_finding,
)
from app.llm.echo import EchoProvider
from app.schemas.common import SourceLocator, new_run_id
from app.schemas.event import EventType
from app.schemas.evidence import EvidenceRef, ResolutionStatus
from app.schemas.finding import Finding
from app.schemas.verification import IssueType, VerificationRequest, VerificationStatus


def _ref(doc: str, row: int, *, resolved: bool = True) -> EvidenceRef:
    return EvidenceRef(
        locator=SourceLocator(document_id=doc, document_name=doc, row=row),
        resolution=ResolutionStatus.RESOLVED if resolved else ResolutionStatus.UNRESOLVED,
        resolution_note="" if resolved else "no task produced this locator",
    )


def _finding(claim: str, refs: list[EvidenceRef]) -> Finding:
    return Finding(finding_id="F-001", claim=claim, evidence=refs)


def _text(*pairs: tuple[str, str]) -> dict[str, str]:
    return dict(pairs)


def _verdict(status: str, issues: list[dict[str, str]] | None = None) -> str:
    return json.dumps({"status": status, "issues": issues or []})


def _verifier(*responses: str) -> BaselineVerifier:
    return BaselineVerifier(EchoProvider(responses={"verification": list(responses)}))


# --- the contract: what a verifier is not shown --------------------------------


def test_the_request_has_no_field_for_the_reasoning_trail() -> None:
    """The absence is the contract, not an oversight."""
    fields = set(VerificationRequest.model_fields)
    forbidden = {
        "reasoning",
        "reasoning_step",
        "reasoning_trace",
        "observations",
        "plan",
        "classification",
        "confidence",
    }
    assert not (fields & forbidden), f"a verifier must not see: {fields & forbidden}"


def test_building_a_request_carries_only_the_claim_and_its_evidence() -> None:
    finding = _finding("Dates conflict.", [_ref("a.txt", 1)])
    finding.classification = finding.classify()

    request = build_request(finding, _text(("a.txt:r1", "completion 2026-04-30")))

    assert request.claim == "Dates conflict."
    assert set(request.evidence_content) == {"a.txt:r1"}
    dumped = request.model_dump()
    assert "classification" not in dumped
    assert "confidence" not in dumped


def test_unresolved_references_contribute_no_content() -> None:
    finding = _finding("Claim.", [_ref("a.txt", 1), _ref("ghost.txt", 9, resolved=False)])
    request = build_request(finding, _text(("a.txt:r1", "text"), ("ghost.txt:r9", "text")))
    assert set(request.evidence_content) == {"a.txt:r1"}


# --- decided without a model ---------------------------------------------------


async def test_a_claim_with_no_resolved_evidence_is_unsupported_without_a_model_call() -> None:
    """Structural, not a matter of judgement. Spending a call to learn nothing was cited
    would be theatre."""
    provider = EchoProvider()
    verifier = BaselineVerifier(provider)

    result = await verifier.verify(
        build_request(_finding("Claim.", [_ref("g.txt", 1, resolved=False)]), {})
    )

    assert result.status is VerificationStatus.UNSUPPORTED
    assert result.issues[0].issue_type is IssueType.NO_EVIDENCE
    assert provider.calls == [], "no model call was needed"


async def test_resolved_references_with_empty_text_are_inconclusive() -> None:
    provider = EchoProvider()
    result = await BaselineVerifier(provider).verify(
        build_request(_finding("Claim.", [_ref("a.txt", 1)]), _text(("a.txt:r1", "   ")))
    )
    assert result.status is VerificationStatus.INCONCLUSIVE
    assert provider.calls == []


# --- verdicts ------------------------------------------------------------------


async def test_a_supported_claim_passes() -> None:
    result = await _verifier(_verdict("SUPPORTED")).verify(
        build_request(
            _finding("Completion was 2026-05-14.", [_ref("a.txt", 1)]),
            _text(("a.txt:r1", "M4 go-live closed 2026-05-14.")),
        )
    )
    assert result.passed
    assert result.status is VerificationStatus.SUPPORTED
    assert result.verifier == "baseline"


async def test_a_contradicted_claim_is_not_actionable() -> None:
    """More evidence cannot rescue a claim the sources refute."""
    result = await _verifier(
        _verdict(
            "CONTRADICTED",
            [{"issue_type": "EVIDENCE_MISMATCH", "description": "the figure shows an overrun"}],
        )
    ).verify(
        build_request(
            _finding("Spend was under budget.", [_ref("a.txt", 1)]),
            _text(("a.txt:r1", "Spend 450,000 against approved 380,000.")),
        )
    )

    assert result.status is VerificationStatus.CONTRADICTED
    assert not result.passed
    assert not result.actionable


async def test_an_unsupported_claim_is_actionable() -> None:
    """Unsupported is a gap to fill; contradicted is not."""
    result = await _verifier(
        _verdict("UNSUPPORTED", [{"issue_type": "NO_EVIDENCE", "description": "nothing cited"}])
    ).verify(
        build_request(_finding("Claim.", [_ref("a.txt", 1)]), _text(("a.txt:r1", "unrelated")))
    )
    assert result.actionable


async def test_a_rejection_always_carries_a_reason() -> None:
    """A verdict with no stated reason cannot be acted on by the replanning loop."""
    result = await _verifier(_verdict("UNSUPPORTED")).verify(
        build_request(_finding("Claim.", [_ref("a.txt", 1)]), _text(("a.txt:r1", "text")))
    )
    assert result.issues, "the schema refuses a rejection with no issue"


async def test_an_unrecognised_verdict_is_inconclusive_not_a_pass() -> None:
    """Defaulting to SUPPORTED would turn a parsing failure into a verified finding."""
    result = await _verifier(_verdict("PROBABLY FINE")).verify(
        build_request(_finding("Claim.", [_ref("a.txt", 1)]), _text(("a.txt:r1", "text")))
    )
    assert result.status is VerificationStatus.INCONCLUSIVE
    assert not result.passed


async def test_an_unrecognised_issue_type_falls_back_rather_than_failing() -> None:
    result = await _verifier(
        _verdict("UNSUPPORTED", [{"issue_type": "MADE_UP", "description": "something"}])
    ).verify(build_request(_finding("Claim.", [_ref("a.txt", 1)]), _text(("a.txt:r1", "text"))))
    assert result.issues[0].issue_type is IssueType.EVIDENCE_MISMATCH


async def test_a_model_failure_leaves_the_finding_unverified() -> None:
    """An unverifiable finding stays unverified. Passing it would be the failure."""
    result = await _verifier("not json", "still not", "nor this").verify(
        build_request(_finding("Claim.", [_ref("a.txt", 1)]), _text(("a.txt:r1", "text")))
    )
    assert result.status is VerificationStatus.INCONCLUSIVE
    assert not result.passed


async def test_the_models_own_confidence_is_discarded() -> None:
    """The model's certainty is the thing being checked; it cannot also be the measure."""
    raw = json.dumps({"status": "SUPPORTED", "issues": [], "confidence": 0.99})
    result = await _verifier(raw).verify(
        build_request(_finding("Claim.", [_ref("a.txt", 1)]), _text(("a.txt:r1", "text")))
    )
    assert result.confidence != 0.99


async def test_more_corroborating_documents_raise_verdict_confidence() -> None:
    single = await _verifier(_verdict("SUPPORTED")).verify(
        build_request(_finding("Claim.", [_ref("a.txt", 1)]), _text(("a.txt:r1", "text")))
    )
    double = await _verifier(_verdict("SUPPORTED")).verify(
        build_request(
            _finding("Claim.", [_ref("a.txt", 1), _ref("b.txt", 2)]),
            _text(("a.txt:r1", "text"), ("b.txt:r2", "text")),
        )
    )
    assert double.confidence > single.confidence


# --- the remote seam -----------------------------------------------------------


async def test_an_unreachable_remote_verifier_degrades_and_says_so() -> None:
    """Degradation is never silent. A finding verified by a fallback is not the same."""
    remote = RemoteVerifier("http://127.0.0.1:1", _verifier(_verdict("SUPPORTED")), timeout_s=2.0)

    result = await remote.verify(
        build_request(_finding("Claim.", [_ref("a.txt", 1)]), _text(("a.txt:r1", "text")))
    )

    assert result.degraded
    assert result.degraded_reason
    assert result.verifier == "baseline"


def test_the_default_provider_satisfies_the_protocol() -> None:
    assert isinstance(build_verification_provider(EchoProvider()), VerificationProvider)


def test_an_unconfigured_remote_provider_falls_back_to_baseline(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.core.config import VerificationProviderName, get_settings

    settings = get_settings()
    monkeypatch.setattr(settings, "verification_provider", VerificationProviderName.REMOTE)
    monkeypatch.setattr(settings, "verification_base_url", "")

    assert isinstance(build_verification_provider(EchoProvider()), BaselineVerifier)


# --- attaching to a finding, and tracing ---------------------------------------


async def test_verifying_attaches_the_result_and_records_it() -> None:
    memory = MemoryEventSink()
    emitter = RunEventEmitter(EventBus([memory]), new_run_id())
    finding = _finding("Completion was 2026-05-14.", [_ref("a.txt", 1)])

    result = await verify_finding(
        _verifier(_verdict("SUPPORTED")),
        finding,
        _text(("a.txt:r1", "closed 2026-05-14")),
        emit=emitter,
    )

    assert finding.verification is result
    assert finding.is_verified
    assert memory.of_type(EventType.FINDING_VERIFIED)


async def test_a_rejected_finding_emits_a_rejection_event() -> None:
    memory = MemoryEventSink()
    emitter = RunEventEmitter(EventBus([memory]), new_run_id())
    finding = _finding("Claim.", [_ref("g.txt", 1, resolved=False)])

    await verify_finding(_verifier(), finding, {}, emit=emitter)

    assert memory.of_type(EventType.FINDING_REJECTED)
    assert not memory.of_type(EventType.FINDING_VERIFIED)


async def test_degradation_is_recorded_on_the_timeline() -> None:
    memory = MemoryEventSink()
    emitter = RunEventEmitter(EventBus([memory]), new_run_id())
    remote = RemoteVerifier("http://127.0.0.1:1", _verifier(_verdict("SUPPORTED")), timeout_s=2.0)

    await verify_finding(
        remote,
        _finding("Claim.", [_ref("a.txt", 1)]),
        _text(("a.txt:r1", "text")),
        emit=emitter,
    )

    degraded = memory.of_type(EventType.VERIFICATION_DEGRADED)
    assert degraded and degraded[0].payload["reason"]
