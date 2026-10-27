"""Confidence, decomposed and explained (Phase 46).

Measured first: 22 of 26 recorded findings sat at exactly 0.85, for two unrelated reasons (one
document scored 0.85 "agreement"; an INFERENCE was capped at 0.85), and verification never moved
confidence - a finding the verifier rejected kept its 0.85. A number that is almost always 0.85, and
the same whether or not the claim survived checking, explains nothing.

So the final confidence is computed from named factors, each with its value, weight and reason
(`.agent/config/confidence.yaml`):

    value = resolution x (sum of weight x factor) - penalties, capped by the classification

- **resolution** - share of citations that resolved: a gate, not a weight;
- **evidence_strength** - how direct the resolved evidence is: a line citation is the line itself, a
  page citation points at a passage somewhere on the page;
- **independence** - how many distinct documents stand behind it;
- **authority** - the mean authority weight of those documents (Phase 45);
- **verification** - the verifier's verdict, discounted when the strong verifier was unavailable;
- **temporal_consistency** - the share of the claim's dates and figures found on its cited lines,
  not checked (and unweighted) when the lines' text is not available;
- **disputed** (penalty) - it cites a line another finding reports as one side of a contradiction.
- **arithmetic** (penalty, v4 Phase 2) - a difference or total the claim states that its own figures
  do not give (`arithmetic.py`).

Entity resolution, named in the plan, is not a factor: nothing in the pipeline resolves entities
across documents yet, and a factor fixed at 1.0 would be decoration. It arrives with the cyber
entities (Phase 52) or not at all.

Applied once, after replanning (`rescore`). The replanning loop's diminishing-returns stop still
reads the simpler value computed during the loop, so the loop behaves exactly as before.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic import Field

from app.core.agent_config import load_yaml
from app.core.config import get_settings
from app.core.logging import get_logger
from app.evidence.authority import get_authority_config, tier_for_name
from app.intelligence.arithmetic import check_arithmetic
from app.intelligence.temporal import find_dates, find_figures
from app.intelligence.trust.specifics import ungrounded_specifics
from app.schemas.common import JarvisModel
from app.schemas.evidence import EvidenceStrength
from app.schemas.finding import (
    _CLASSIFICATION_CEILING,
    _STRENGTH_WEIGHT,
    Confidence,
    ConfidenceFactor,
    Finding,
    FindingClassification,
    StatementType,
)
from app.schemas.trust import EvidenceText

log = get_logger(__name__)


class ConfidenceConfig(JarvisModel):
    weights: dict[str, float] = Field(
        default_factory=lambda: {
            "evidence_strength": 0.20,
            "independence": 0.25,
            "authority": 0.10,
            "verification": 0.35,
            "temporal_consistency": 0.10,
        }
    )
    independence: dict[str, float] = Field(
        default_factory=lambda: {
            "one_document": 0.6,
            "two_documents": 0.85,
            "three_or_more": 1.0,
        }
    )
    verification: dict[str, float] = Field(
        default_factory=lambda: {
            "SUPPORTED": 1.0,
            "PARTIALLY_SUPPORTED": 0.6,
            "INCONCLUSIVE": 0.4,
            "UNVERIFIED": 0.4,
            "UNSUPPORTED": 0.0,
            "CONTRADICTED": 0.0,
            "degraded_factor": 0.8,
        }
    )
    penalties: dict[str, float] = Field(default_factory=lambda: {"disputed": 0.15})
    # The most a finding can show when the verifier rejected it, whatever else is in its favour.
    verdict_caps: dict[str, float] = Field(
        default_factory=lambda: {"UNSUPPORTED": 0.3, "CONTRADICTED": 0.1}
    )


def get_confidence_config() -> ConfidenceConfig:
    return _load(str(get_settings().agent_dir))


@lru_cache
def _load(agent_dir: str) -> ConfidenceConfig:
    if not (Path(agent_dir) / "config" / "confidence.yaml").exists():
        return ConfidenceConfig()
    raw = load_yaml("confidence.yaml")
    raw.pop("version", None)
    return ConfidenceConfig.model_validate(raw)


def _authority_weight(document: str, authority: dict[str, str] | None) -> tuple[float, str]:
    tier_id = (authority or {}).get(document) or tier_for_name(document)[0]
    tier = get_authority_config().tier(tier_id)
    return (tier.weight if tier else 0.75), tier_id


def assess(
    finding: Finding,
    *,
    authority: dict[str, str] | None = None,
    evidence_text: dict[str, str] | None = None,
    disputed_by: list[str] | None = None,
) -> Confidence:
    """The decomposed confidence for a finding whose evidence and verification are final."""
    config = get_confidence_config()
    cited = len(finding.evidence)
    resolved = [r for r in finding.evidence if r.is_resolved]
    if not resolved:
        return Confidence.none()

    rate = len(resolved) / cited
    resolution = ConfidenceFactor(
        name="resolution",
        value=rate,
        reason=f"{len(resolved)} of {cited} citation(s) resolved against what the run read",
    )

    # A line citation is the evidence itself; a page citation points at a passage somewhere on the
    # page - the weight `EvidenceStrength.CORROBORATING` already carries.
    lines = sum(1 for r in resolved if r.locator.page is None)
    pages = len(resolved) - lines
    strength = (
        lines * _STRENGTH_WEIGHT[EvidenceStrength.DIRECT]
        + pages * _STRENGTH_WEIGHT[EvidenceStrength.CORROBORATING]
    ) / len(resolved)
    w = config.weights

    documents = sorted({r.locator.document_id for r in resolved})
    count = len(documents)
    independence_value = config.independence[
        "one_document" if count == 1 else "two_documents" if count == 2 else "three_or_more"
    ]

    tiers = [_authority_weight(d, authority) for d in documents]
    authority_value = sum(weight for weight, _ in tiers) / len(tiers)
    tier_names = ", ".join(
        f"{d} {tier.lower()}" for d, (_, tier) in zip(documents, tiers, strict=True)
    )

    verification = finding.verification
    status = verification.status.value if verification else "UNVERIFIED"
    verification_value = config.verification.get(status, 0.4)
    verification_reason = f"verifier: {status.replace('_', ' ').lower()}"
    if verification is not None and verification.degraded:
        verification_value *= config.verification.get("degraded_factor", 0.8)
        verification_reason += " by the baseline checker (the strong verifier was unavailable)"

    temporal = _temporal(finding, evidence_text)

    weighted = [
        ConfidenceFactor(
            name="evidence_strength",
            value=strength,
            weight=w.get("evidence_strength", 0.0),
            reason=f"{lines} line citation(s), {pages} page citation(s) (a page is the passage, "
            "not the line)",
        ),
        ConfidenceFactor(
            name="independence",
            value=independence_value,
            weight=w.get("independence", 0.0),
            reason=f"{count} distinct document(s): {', '.join(documents)}",
        ),
        ConfidenceFactor(
            name="authority",
            value=authority_value,
            weight=w.get("authority", 0.0),
            reason=f"mean source authority: {tier_names}",
        ),
        ConfidenceFactor(
            name="verification",
            value=verification_value,
            weight=w.get("verification", 0.0),
            reason=verification_reason,
        ),
        temporal.model_copy(update={"weight": w.get("temporal_consistency", 0.0)}),
    ]

    penalties = (
        [
            ConfidenceFactor(
                name="disputed",
                value=config.penalties.get("disputed", 0.15),
                reason=f"a line it cites is one side of a contradiction ({', '.join(disputed_by)})",
            )
        ]
        if disputed_by
        else []
    )
    # Its own arithmetic, redone (v4 Phase 2): a difference or total its figures do not give.
    arithmetic = check_arithmetic(finding.claim)
    if not arithmetic.holds:
        penalties.append(
            ConfidenceFactor(
                name="arithmetic",
                value=config.penalties.get("arithmetic", 0.3),
                reason=f"its arithmetic does not hold: {arithmetic.reason}",
            )
        )

    ceiling = _CLASSIFICATION_CEILING[finding.classification]
    cap_reason = ""
    verdict_cap = config.verdict_caps.get(status)
    if verdict_cap is not None and verdict_cap < ceiling:
        ceiling = verdict_cap
        cap_reason = f"the verifier found it {status.lower()}"
    return Confidence.from_factors(
        resolution=resolution,
        weighted=weighted,
        penalties=penalties,
        ceiling=ceiling,
        evidence_strength=strength,
        source_agreement=independence_value,
        cap_reason=cap_reason,
    )


def _temporal(finding: Finding, evidence_text: dict[str, str] | None) -> ConfidenceFactor:
    """The share of the claim's dates and figures that appear on its own cited lines."""
    specifics = len(find_dates(finding.claim)) + len(find_figures(finding.claim))
    if specifics == 0:
        return ConfidenceFactor(
            name="temporal_consistency",
            value=1.0,
            reason="the claim states no date or figure to check",
        )
    if evidence_text is None:
        return ConfidenceFactor(
            name="temporal_consistency",
            value=1.0,
            assessed=False,
            reason="not checked: the cited lines' text was not available",
        )
    cited = [
        EvidenceText(source=ref.as_ref(), content=evidence_text.get(ref.as_ref(), ""))
        for ref in finding.evidence
        if ref.is_resolved
    ]
    missing = ungrounded_specifics(finding.claim, cited)
    found = max(0, specifics - len(missing))
    return ConfidenceFactor(
        name="temporal_consistency",
        value=found / specifics,
        reason=(
            f"{found} of {specifics} date(s) and figure(s) in the claim are on its cited lines"
            + (f"; not found: {', '.join(missing)}" if missing else "")
        ),
    )


def rescore(
    findings: list[Finding],
    *,
    authority: dict[str, str] | None = None,
    evidence_text: dict[str, str] | None = None,
) -> None:
    """Give every final finding its decomposed confidence, in place (Phase 46)."""
    contested: dict[str, list[str]] = {}
    for finding in findings:
        if finding.statement_type is StatementType.CONTRADICTION:
            for ref in finding.evidence:
                if ref.is_resolved:
                    contested.setdefault(ref.as_ref(), []).append(finding.finding_id)
    for finding in findings:
        # A verified claim from two or more documents is a FACT (Phase 45's basis). Its internal
        # classification can still read INFERENCE - the verifier confirmed it without decomposing
        # it into elements - and the INFERENCE cap (0.85) then ranked it below a single-document
        # claim. Measured on the recorded runs; raised here, after the loop, where nothing reads it
        # to decide what to do next.
        if (
            finding.statement_basis is StatementType.FACT
            and finding.classification is FindingClassification.INFERENCE
        ):
            finding.classification = FindingClassification.FACT
        disputed = (
            []
            if finding.statement_type is StatementType.CONTRADICTION
            else sorted(
                {
                    other
                    for ref in finding.evidence
                    if ref.is_resolved
                    for other in contested.get(ref.as_ref(), [])
                }
            )
        )
        finding.confidence = assess(
            finding, authority=authority, evidence_text=evidence_text, disputed_by=disputed
        )


def why(finding: Finding) -> list[str]:
    """Why this confidence, and why not higher, in sentences whose numbers add up (Phase 46)."""
    confidence = finding.confidence
    if not confidence.factors:
        return [confidence.explain()] if confidence.value else ["Nothing it cites resolved."]
    by_name = {f.name: f for f in confidence.factors}
    resolution = by_name["resolution"]
    weighted = [f for f in confidence.factors if f.weight > 0]
    terms = " + ".join(
        f"{f.name.replace('_', ' ')} {f.weight:.2f} x {f.value:.2f}" for f in weighted
    )
    lines = [
        f"Weighted evidence {confidence.weighted:.2f} = {terms}.",
        f"Resolution {resolution.value:.2f} x {confidence.weighted:.2f} = "
        f"{resolution.value * confidence.weighted:.2f} ({resolution.reason}).",
    ]
    if confidence.penalty:
        lines.append(
            f"Minus {confidence.penalty:.2f} for "
            + "; ".join(
                f.reason for f in confidence.factors if f.contribution < 0 and f.weight == 0
            )
            + "."
        )
    uncapped = resolution.value * confidence.weighted - confidence.penalty
    if uncapped > confidence.classification_ceiling + 1e-9:
        lines.append(
            f"Capped at {confidence.classification_ceiling:.2f}: "
            + (
                f"{confidence.cap_reason}."
                if confidence.cap_reason
                else f"a {finding.classification.value} cannot present as more certain."
            )
        )
    lines.append(f"Confidence {confidence.value:.2f}.")

    # Why not higher: what each factor cost, largest first.
    costs = sorted(
        ((resolution.value * f.weight * (1.0 - f.value), f) for f in weighted if f.value < 1.0),
        key=lambda pair: pair[0],
        reverse=True,
    )
    for cost, factor in costs:
        if cost >= 0.005:
            lines.append(
                f"Not higher: {factor.name.replace('_', ' ')} {factor.value:.2f} cost {cost:.2f} "
                f"({factor.reason})."
            )
    if resolution.value < 1.0:
        lines.append(
            f"Not higher: resolution {resolution.value:.2f} cost "
            f"{(1.0 - resolution.value) * confidence.weighted:.2f} ({resolution.reason})."
        )
    unassessed = [f for f in confidence.factors if not f.assessed]
    for factor in unassessed:
        lines.append(f"Not counted: {factor.name.replace('_', ' ')} - {factor.reason}.")
    return lines
