"""Competing explanations, tested against the findings (Phase 47).

A hypothesis is an explanation the evidence might or might not support - "the outage was caused by
the configuration change" against "by the power dip". The model proposes them; it does not rank
them. Each is tested against the run's verified findings, and its support is computed from those
findings' confidence. Nothing here is a probability a model asserted (invariant 9 and the v2 plan's
"changed from the review").

A question the evidence cannot settle ends with two or more hypotheses OPEN, each with what would
decide it and where to look next. Closing it anyway would be a premature conclusion - the failure
`premature_conclusion_rate` measures.
"""

from __future__ import annotations

from enum import StrEnum

from pydantic import Field

from app.schemas.common import JarvisModel


class HypothesisStatus(StrEnum):
    # Clearly ahead of every other on verified evidence.
    SUPPORTED = "SUPPORTED"
    # Not settled: the evidence does not separate it from the others.
    OPEN = "OPEN"
    # A verified finding contradicts it more than any supports it.
    REJECTED = "REJECTED"


class Relation(StrEnum):
    SUPPORTS = "SUPPORTS"
    CONTRADICTS = "CONTRADICTS"
    NEUTRAL = "NEUTRAL"


class NextEvidenceKind(StrEnum):
    # Lines in the attached documents worth reading next: a search the run can do.
    SEARCH = "SEARCH"
    # Nothing attached bears on it: evidence a person has to provide.
    ANALYST_REQUEST = "ANALYST_REQUEST"


class Lead(JarvisModel):
    """A line the next-evidence search found. A lead, not a finding: nothing has checked it."""

    locator: str
    text: str


class NextEvidence(JarvisModel):
    kind: NextEvidenceKind
    # In plain language: what to look at, or what to ask for.
    text: str
    query: str = ""
    leads: list[Lead] = Field(default_factory=list)


class FindingRelation(JarvisModel):
    finding_id: str
    relation: Relation
    # The finding's confidence when tested; the support is the sum of these.
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)


class Hypothesis(JarvisModel):
    hypothesis_id: str = Field(pattern=r"^H-\d+$")
    statement: str
    supporting: list[FindingRelation] = Field(default_factory=list)
    contradicting: list[FindingRelation] = Field(default_factory=list)
    # Computed: confidence of the verified findings for it, minus those against it.
    support: float = 0.0
    against: float = 0.0
    status: HypothesisStatus = HypothesisStatus.OPEN
    status_reason: str = ""
    # What would decide it, as the model put it - shown, never acted on unchecked.
    decisive_evidence: str = ""
    next_evidence: NextEvidence | None = None

    @property
    def net(self) -> float:
        return self.support - self.against


class HypothesisSet(JarvisModel):
    """The run's competing explanations, ranked by computed support, or why there are none."""

    question: str = ""
    hypotheses: list[Hypothesis] = Field(default_factory=list)
    # True when exactly one explanation is supported and the rest are not.
    determined: bool = False
    summary: str = ""
    # Why the step did not run or produced nothing: not an explanation question, too few proposals.
    skipped_reason: str = ""
    llm_calls: int = 0

    @property
    def open(self) -> list[Hypothesis]:
        return [h for h in self.hypotheses if h.status is HypothesisStatus.OPEN]
