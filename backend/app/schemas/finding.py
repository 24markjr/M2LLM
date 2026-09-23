"""Findings: the unit of output.

Two things in this module carry architectural weight:

**`Confidence` cannot be constructed without its components.** There is no way to write
`confidence=0.96`. You must supply resolution rate, evidence strength, source agreement and
classification, and the value is derived from them. This is how "confidence is computed,
never asked for" stops being a policy someone has to remember and becomes something the type
system enforces. A model's self-reported certainty has nowhere to go.

**Classification is a consequence, not a declaration.** `FACT` requires that every claim
element resolved. The reasoning engine may propose a classification, but
`Finding.classify()` recomputes it from the evidence, and the stricter answer wins.
"""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum

from pydantic import Field, model_validator

from app.schemas.common import (
    FindingId,
    JarvisModel,
    NonEmptyStr,
    UnitFloat,
    utcnow,
)
from app.schemas.evidence import (
    ClaimElement,
    EvidenceGap,
    EvidenceRef,
    EvidenceStrength,
)
from app.schemas.verification import VerificationResult, VerificationStatus


class FindingClassification(StrEnum):
    """How much epistemic weight a claim is entitled to."""

    # Every element traces to resolved evidence.
    FACT = "FACT"
    # Combines two or more resolved sources with a stated reasoning step.
    INFERENCE = "INFERENCE"
    # Partially supported: at least one element is unresolved.
    HYPOTHESIS = "HYPOTHESIS"
    # No resolved evidence at all.
    UNKNOWN = "UNKNOWN"


# Relative weight of each evidence strength when scoring support.
_STRENGTH_WEIGHT: dict[EvidenceStrength, float] = {
    EvidenceStrength.DIRECT: 1.0,
    EvidenceStrength.CORROBORATING: 0.7,
    EvidenceStrength.CIRCUMSTANTIAL: 0.4,
    EvidenceStrength.CONTRADICTORY: 0.0,
}

# Ceiling applied per classification. A HYPOTHESIS cannot present as near-certain no matter
# how strong the evidence behind its resolved parts happens to be.
_CLASSIFICATION_CEILING: dict[FindingClassification, float] = {
    FindingClassification.FACT: 1.0,
    FindingClassification.INFERENCE: 0.85,
    FindingClassification.HYPOTHESIS: 0.4,
    FindingClassification.UNKNOWN: 0.2,
}


class Confidence(JarvisModel):
    """A computed confidence, inseparable from the inputs that produced it.

    Constructed only via `Confidence.compute(...)`. The components travel with the value, so
    any report, UI or evaluation can show *why* a number is what it is — and so a value that
    looks wrong can be traced rather than argued about.
    """

    value: UnitFloat
    # Share of cited references that resolved against retrieved content.
    resolution_rate: UnitFloat
    # Weighted strength of the resolved evidence.
    evidence_strength: UnitFloat
    # Agreement across independent sources. Low when sources conflict.
    source_agreement: UnitFloat
    # The ceiling that was applied, for transparency about why a value was capped.
    classification_ceiling: UnitFloat = 1.0

    @classmethod
    def compute(
        cls,
        *,
        refs: list[EvidenceRef],
        strengths: list[EvidenceStrength] | None = None,
        source_agreement: float = 1.0,
        classification: FindingClassification = FindingClassification.UNKNOWN,
    ) -> Confidence:
        """Derive confidence from evidence. The only way to make one.

        Deliberately a pure function: the same evidence always yields the same number, which
        is what allows Phase 20 to treat confidence as a measurable property rather than
        model noise.
        """
        total = len(refs)
        resolved = [r for r in refs if r.is_resolved]
        resolution_rate = (len(resolved) / total) if total else 0.0

        if strengths:
            weights = [_STRENGTH_WEIGHT[s] for s in strengths]
            strength_score = sum(weights) / len(weights)
        elif resolved:
            # No strength assessment supplied: assume direct, since the reference resolved.
            strength_score = 1.0
        else:
            strength_score = 0.0

        agreement = max(0.0, min(1.0, source_agreement))
        ceiling = _CLASSIFICATION_CEILING[classification]

        raw = resolution_rate * strength_score * agreement
        return cls(
            value=min(raw, ceiling),
            resolution_rate=resolution_rate,
            evidence_strength=strength_score,
            source_agreement=agreement,
            classification_ceiling=ceiling,
        )

    @classmethod
    def none(cls) -> Confidence:
        """Zero confidence, for a claim with nothing behind it."""
        return cls(
            value=0.0,
            resolution_rate=0.0,
            evidence_strength=0.0,
            source_agreement=0.0,
            classification_ceiling=_CLASSIFICATION_CEILING[FindingClassification.UNKNOWN],
        )

    def explain(self) -> str:
        """One line suitable for a report footnote or a UI tooltip."""
        return (
            f"{self.value:.2f} "
            f"(resolved {self.resolution_rate:.0%}, "
            f"strength {self.evidence_strength:.2f}, "
            f"agreement {self.source_agreement:.2f}, "
            f"cap {self.classification_ceiling:.2f})"
        )


class Finding(JarvisModel):
    """A structured claim, with everything needed to judge whether to believe it."""

    finding_id: FindingId
    claim: NonEmptyStr
    classification: FindingClassification = FindingClassification.UNKNOWN
    evidence: list[EvidenceRef] = Field(default_factory=list)
    confidence: Confidence = Field(default_factory=Confidence.none)

    # Set by the decomposer (Phase 14). Element-level support is what makes gaps specific.
    elements: list[ClaimElement] = Field(default_factory=list)
    gaps: list[EvidenceGap] = Field(default_factory=list)

    verification: VerificationResult | None = None

    # Provenance.
    derived_from_task_ids: list[str] = Field(default_factory=list)
    # Which replan iteration produced or last revised this. 0 = the original pass.
    revision: int = Field(default=0, ge=0)
    created_at: datetime = Field(default_factory=utcnow)

    # --- Derived state ---------------------------------------------------------

    # Plain properties, deliberately NOT @computed_field. A computed field is serialized
    # into the model's JSON, and with extra="forbid" the model then rejects its own output
    # on re-validation - which would break persistence, trace replay and the evaluation
    # harness's reconstruction of stored runs. Derived values belong in API response models,
    # not in the wire contract of a stored object.
    @property
    def resolved_evidence_count(self) -> int:
        return sum(1 for e in self.evidence if e.is_resolved)

    @property
    def has_resolved_evidence(self) -> bool:
        return self.resolved_evidence_count > 0

    @property
    def is_verified(self) -> bool:
        return self.verification is not None and self.verification.passed

    @property
    def is_rejected(self) -> bool:
        """Contradicted claims are rejected outright.

        Distinct from merely unverified: more evidence will not rescue a claim the sources
        refute, so this is not a gap to fill. It belongs in the report's Rejected section.
        """
        return (
            self.verification is not None
            and self.verification.status is VerificationStatus.CONTRADICTED
        )

    @property
    def needs_investigation(self) -> bool:
        """Whether the replanning loop should try to improve this finding."""
        if self.verification is None:
            return False
        return self.verification.actionable and bool(self.unresolved_gaps)

    @property
    def unresolved_gaps(self) -> list[EvidenceGap]:
        return [g for g in self.gaps if not g.resolved]

    # --- Recomputation ---------------------------------------------------------

    def classify(self) -> FindingClassification:
        """Derive the classification from the evidence, ignoring any prior claim to one.

        The reasoning engine's proposed classification is a suggestion. This is the ruling.
        """
        if not self.evidence or self.resolved_evidence_count == 0:
            return FindingClassification.UNKNOWN

        all_elements_supported = bool(self.elements) and all(e.supported for e in self.elements)
        has_unresolved = any(not e.is_resolved for e in self.evidence)

        if has_unresolved:
            return FindingClassification.HYPOTHESIS

        # Distinct source documents behind the resolved evidence.
        sources = {e.locator.document_id for e in self.evidence if e.is_resolved}

        if all_elements_supported and not has_unresolved:
            return FindingClassification.FACT
        if len(sources) >= 2:
            return FindingClassification.INFERENCE
        if self.elements and not all_elements_supported:
            return FindingClassification.HYPOTHESIS
        return FindingClassification.FACT

    @model_validator(mode="after")
    def _confidence_cannot_exceed_classification(self) -> Finding:
        ceiling = _CLASSIFICATION_CEILING[self.classification]
        if self.confidence.value > ceiling + 1e-9:
            raise ValueError(
                f"confidence {self.confidence.value:.3f} exceeds the ceiling "
                f"{ceiling:.2f} for classification {self.classification.value}"
            )
        return self

    @model_validator(mode="after")
    def _facts_need_resolved_evidence(self) -> Finding:
        if self.classification is FindingClassification.FACT and self.resolved_evidence_count == 0:
            raise ValueError(
                "a FACT requires at least one resolved evidence reference - "
                "this is the invariant the whole architecture exists to protect"
            )
        return self
