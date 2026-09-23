"""Evidence, and the absence of it.

This module carries the project's central idea. Two distinctions do most of the work:

1. **`EvidenceRef` vs `Evidence`** — a reference is what a claim *cites*; evidence is what
   was actually *found*. A citation that cannot be matched to retrieved content becomes an
   `UNRESOLVED` reference, which is recorded rather than discarded. That single rule is what
   turns "the model cited something" into a checkable fact.

2. **`EvidenceGap`** — a specific, named element that available evidence does not support.
   Not "insufficient evidence", but "the approved baseline completion date". The difference
   is what makes the gap actionable: a named element can be turned into a retrieval query.
"""

from __future__ import annotations

from enum import StrEnum

from pydantic import Field, model_validator

from app.schemas.common import (
    EvidenceId,
    GapId,
    JarvisModel,
    NonEmptyStr,
    SourceLocator,
    UnitFloat,
)


class ResolutionStatus(StrEnum):
    """Whether a citation was matched against content the system actually retrieved."""

    RESOLVED = "RESOLVED"
    UNRESOLVED = "UNRESOLVED"
    # Cited location exists, but its content does not say what the claim says it says.
    MISMATCHED = "MISMATCHED"


class EvidenceStrength(StrEnum):
    """How much weight a piece of evidence can carry.

    `DIRECT` means the source states the claim. `CIRCUMSTANTIAL` means it is consistent with
    it. Collapsing these would let a pile of weak agreement masquerade as proof.
    """

    DIRECT = "DIRECT"
    CORROBORATING = "CORROBORATING"
    CIRCUMSTANTIAL = "CIRCUMSTANTIAL"
    CONTRADICTORY = "CONTRADICTORY"


class EvidenceRef(JarvisModel):
    """A pointer from a claim to a source location.

    Produced when a claim is made. Resolution happens afterwards, in the binder (Phase 13) —
    which is precisely why `resolution` defaults to `UNRESOLVED`: nothing counts as resolved
    until something has checked it.
    """

    evidence_id: EvidenceId | None = None
    locator: SourceLocator
    resolution: ResolutionStatus = ResolutionStatus.UNRESOLVED
    # Why resolution failed, when it did. Feeds gap detection.
    resolution_note: str = ""

    @property
    def is_resolved(self) -> bool:
        return self.resolution is ResolutionStatus.RESOLVED

    def as_ref(self) -> str:
        return self.locator.as_ref()


class Evidence(JarvisModel):
    """Retrieved content that bears on a claim, with where it came from."""

    evidence_id: EvidenceId
    locator: SourceLocator
    content: NonEmptyStr = Field(description="The actual text, quoted, not paraphrased")
    strength: EvidenceStrength = EvidenceStrength.DIRECT
    relevance_score: UnitFloat = 1.0
    # Which retrieval produced this. Makes an evidence item traceable to a task.
    retrieved_by_task_id: str | None = None

    def to_ref(self) -> EvidenceRef:
        return EvidenceRef(
            evidence_id=self.evidence_id,
            locator=self.locator,
            resolution=ResolutionStatus.RESOLVED,
        )


class GapType(StrEnum):
    """Why a claim element is unsupported. The type determines how to go and fix it."""

    # Nothing in scope addresses this element at all.
    MISSING_SOURCE = "MISSING_SOURCE"
    # A comparison was made against something that was never established as the baseline.
    MISSING_BASELINE = "MISSING_BASELINE"
    # A citation was made but could not be matched to retrieved content.
    UNRESOLVED_CITATION = "UNRESOLVED_CITATION"
    # Two sources disagree and nothing breaks the tie.
    CONFLICTING_SOURCES = "CONFLICTING_SOURCES"
    # Support exists but is too coarse — "Q2" cannot support a claim about a specific date.
    INSUFFICIENT_GRANULARITY = "INSUFFICIENT_GRANULARITY"
    # Support exists but predates a revision that may have superseded it.
    STALE_SOURCE = "STALE_SOURCE"


class ClaimElement(JarvisModel):
    """One verifiable part of a claim.

    Decomposition is what makes gaps specific. "The project slipped two weeks against the
    approved baseline" contains a duration, a baseline and a comparison; checking support
    per element is how the system can say *which* part is unsupported rather than shrugging
    at the whole claim.
    """

    text: NonEmptyStr
    kind: str = Field(default="assertion", description="entity | quantity | date | relation")
    supported: bool = False
    supporting_refs: list[EvidenceRef] = Field(default_factory=list)


class EvidenceGap(JarvisModel):
    """A specific missing piece of support, and what would close it.

    `missing` is written for a human to read: it appears in the UI and in the report's
    Limitations section. A gap that says "more evidence needed" has failed at its job.
    """

    gap_id: GapId
    finding_id: str
    gap_type: GapType
    missing: NonEmptyStr = Field(
        description="The specific absent element, e.g. 'approved baseline completion date'"
    )
    element: ClaimElement | None = None
    # How much resolving this would improve the finding — drives Phase 17 prioritisation.
    severity: UnitFloat = 0.5
    # A concrete query, not a restatement of the gap. Phrased by the model; the decision
    # that a gap exists is deterministic and made before this is ever asked for.
    suggested_query: str = ""
    suggested_scope: list[str] = Field(default_factory=list)
    resolved: bool = False
    resolved_by_task_id: str | None = None

    @model_validator(mode="after")
    def _resolved_gaps_name_their_task(self) -> EvidenceGap:
        if self.resolved and not self.resolved_by_task_id:
            raise ValueError(
                "a resolved gap must name the task that resolved it - otherwise the "
                "replanning loop cannot be audited"
            )
        return self
