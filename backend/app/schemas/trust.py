"""Lexical claim verification, answer-level grounding, and prompt-injection scanning.

Ported from Member 4 (`Mem-4/schemas.py`, `trust/`, `security/`). The status vocabulary is
theirs and is kept unchanged. It is not JARVIS's `VerificationStatus`: Member 4 distinguishes
"no evidence at all" (`INSUFFICIENT_EVIDENCE`) from "evidence that does not confirm the detail"
(`UNSUPPORTED`). The adapter in `app/integrations/verification.py` maps one onto the other, and
that mapping is the only place the two vocabularies meet.

See `.claude/integrations/teammate-port.md`, features T1-T9.
"""

from __future__ import annotations

from enum import StrEnum

from pydantic import Field

from app.schemas.common import JarvisModel, NonEmptyStr, UnitFloat


class TrustStatus(StrEnum):
    """Member 4's `ClaimStatus`, unchanged."""

    SUPPORTED = "SUPPORTED"
    CONTRADICTED = "CONTRADICTED"
    UNSUPPORTED = "UNSUPPORTED"
    INSUFFICIENT_EVIDENCE = "INSUFFICIENT_EVIDENCE"
    # Produced only by answer-level evaluation, never for a single claim. Same as the original.
    PARTIALLY_SUPPORTED = "PARTIALLY_SUPPORTED"


class EvidenceText(JarvisModel):
    """One item of the evidence pool: where it came from, and what it says."""

    source: NonEmptyStr
    content: str


class ScoredEvidence(JarvisModel):
    source: NonEmptyStr
    relevance: UnitFloat
    relevant: bool
    conflicts: bool = False
    # Why it conflicts, when it does: "times 11:40 vs 13:15 on shared id 4821".
    conflict_reason: str = ""


class LexicalThresholds(JarvisModel):
    """The original's three thresholds. Configured in `agent.yaml:verification.lexical`."""

    # Evidence below this is not about the claim at all.
    relevance: UnitFloat = 0.2
    # Relevant evidence at or above this confirms the claim.
    support: UnitFloat = 0.4
    # A conflict is only believed on evidence this close to the claim, so an unrelated number
    # elsewhere in a document cannot contradict it.
    conflict: UnitFloat = 0.5


class LexicalVerdict(JarvisModel):
    """The outcome of checking one claim against an evidence pool."""

    claim: NonEmptyStr
    status: TrustStatus
    reasoning: NonEmptyStr
    # The best relevance score involved in the decision, as the original reported it.
    relevance_score: UnitFloat = 0.0
    supporting: list[str] = Field(default_factory=list)
    contradicting: list[str] = Field(default_factory=list)
    scored: list[ScoredEvidence] = Field(default_factory=list)


class AnswerAssessment(JarvisModel):
    """A whole generated answer, split into sentences, each one verified.

    Catches an answer that mixes one true statement with one invented one, which a
    whole-answer score would average away.
    """

    answer: str
    overall: TrustStatus
    claims: list[LexicalVerdict] = Field(default_factory=list)


class InjectionSeverity(StrEnum):
    """Member 4's severity levels, unchanged."""

    NONE = "NONE"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"


class InjectionScan(JarvisModel):
    """What a scan of one untrusted text found.

    A hit is not a verdict that the document is malicious. A security report quoting an attack
    matches too. Hits are reported and the content is still read, as data, because dropping a
    document on a pattern match would let an attacker delete evidence by quoting a phrase.
    """

    source: str = ""
    # category -> the phrases that matched
    hits: dict[str, list[str]] = Field(default_factory=dict)
    severity: InjectionSeverity = InjectionSeverity.NONE

    @property
    def flagged(self) -> bool:
        return bool(self.hits)
