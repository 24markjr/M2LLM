"""Lexical claim verification: Member 4's verifier, ported.

Ported from `Mem-4/trust/verifier.py:verify_claim` and `_conflicts`. The decision procedure is
the original's, step for step:

1. Empty pool → `INSUFFICIENT_EVIDENCE`.
2. Score every item by TF-IDF cosine. Nothing at or above `relevance` (0.2) →
   `INSUFFICIENT_EVIDENCE`.
3. Any relevant item that **conflicts** → `CONTRADICTED`.
4. Any relevant item at or above `support` (0.4) → `SUPPORTED`.
5. Otherwise → `UNSUPPORTED`.

The conflict rule is the original's safeguard: claim and evidence must share an identifying
number (3+ digits, a shipment id, an invoice number) **and** disagree on time, and the evidence
must score at least `conflict` (0.5). Sharing an id is what makes them about the same thing.
Without it, any two statements with different times would contradict each other.

Three deviations, each recorded in `.claude/integrations/teammate-port.md` (T3/T4) with what it
changed on the original benchmark:

- **Dates conflict as well as times.** The original only compared clock times, so "arrived 20
  September" against "arrived 14 September" was never `CONTRADICTED`. Disjoint dates on a shared
  id now count, with the same relevance requirement.
- **Times compare by the minute they denote.** `11:40` and `11:40 AM` were different strings and
  so a conflict.
- **A year inside a date is not an identifier.** "2026" in two unrelated dated statements made
  them share an id.
"""

from __future__ import annotations

from app.intelligence.temporal import (
    dates_disjoint,
    find_dates,
    find_times,
    identifiers,
    times_disjoint,
)
from app.intelligence.trust.tfidf import relevance_scores
from app.schemas.knowledge import PartialDate
from app.schemas.trust import (
    EvidenceText,
    LexicalThresholds,
    LexicalVerdict,
    ScoredEvidence,
    TrustStatus,
)


def conflict_reason(claim: str, evidence: str, relevance: float, conflict_threshold: float) -> str:
    """Why `evidence` contradicts `claim`, or "" if it does not.

    The original's `_conflicts`, returning the reason rather than a bare boolean so the verdict
    can say what disagreed.
    """
    if relevance < conflict_threshold:
        return ""

    shared = identifiers(claim) & identifiers(evidence)
    if not shared:
        # Not clearly about the same thing, so a different time is not a contradiction.
        return ""
    ids = ", ".join(sorted(shared))

    claim_times, evidence_times = find_times(claim), find_times(evidence)
    if times_disjoint(claim_times, evidence_times):
        return f"times {_times(claim_times)} vs {_times(evidence_times)} on shared id {ids}"

    claim_dates = _dates(claim)
    evidence_dates = _dates(evidence)
    if dates_disjoint(claim_dates, evidence_dates):
        return (
            f"dates {', '.join(d.iso() for d in claim_dates)} vs "
            f"{', '.join(d.iso() for d in evidence_dates)} on shared id {ids}"
        )
    return ""


def verify_claim(
    claim: str,
    evidence: list[EvidenceText],
    thresholds: LexicalThresholds | None = None,
) -> LexicalVerdict:
    """Check one claim against a pool of evidence. Deterministic, offline, no model."""
    limits = thresholds or LexicalThresholds()

    if not evidence:
        return LexicalVerdict(
            claim=claim,
            status=TrustStatus.INSUFFICIENT_EVIDENCE,
            reasoning="Evidence pool is empty.",
        )

    scores = relevance_scores(claim, [e.content for e in evidence])
    scored: list[ScoredEvidence] = []
    for item, score in zip(evidence, scores, strict=True):
        is_relevant = score >= limits.relevance
        reason = conflict_reason(claim, item.content, score, limits.conflict) if is_relevant else ""
        scored.append(
            ScoredEvidence(
                source=item.source,
                relevance=score,
                relevant=is_relevant,
                conflicts=bool(reason),
                conflict_reason=reason,
            )
        )

    relevant = [s for s in scored if s.relevant]
    if not relevant:
        return LexicalVerdict(
            claim=claim,
            status=TrustStatus.INSUFFICIENT_EVIDENCE,
            reasoning="No evidence in the pool is topically relevant to this claim.",
            relevance_score=max(scores),
            scored=scored,
        )

    conflicting = [s for s in relevant if s.conflicts]
    if conflicting:
        return LexicalVerdict(
            claim=claim,
            status=TrustStatus.CONTRADICTED,
            reasoning=(
                "Relevant evidence disagrees with the claim. Conflicting source(s): "
                + "; ".join(f"{s.source} ({s.conflict_reason})" for s in conflicting)
            ),
            relevance_score=max(s.relevance for s in conflicting),
            supporting=[s.source for s in relevant if not s.conflicts],
            contradicting=[s.source for s in conflicting],
            scored=scored,
        )

    top = max(s.relevance for s in relevant)
    supporting = [s for s in relevant if s.relevance >= limits.support]
    if supporting:
        return LexicalVerdict(
            claim=claim,
            status=TrustStatus.SUPPORTED,
            reasoning="Supported by: " + ", ".join(s.source for s in supporting),
            relevance_score=top,
            supporting=[s.source for s in supporting],
            scored=scored,
        )

    return LexicalVerdict(
        claim=claim,
        status=TrustStatus.UNSUPPORTED,
        reasoning=(
            "Related evidence exists but does not directly confirm the claim's specific detail."
        ),
        relevance_score=top,
        supporting=[s.source for s in relevant],
        scored=scored,
    )


def _dates(text: str) -> list[PartialDate]:
    return [date for _, date in find_dates(text)]


def _times(times: list[tuple[int, int, bool]]) -> str:
    return ", ".join(f"{h:02d}:{m:02d}" for h, m, _ in times)
