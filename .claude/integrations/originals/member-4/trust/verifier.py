"""
trust/verifier.py
Verifies a claim against a pool of Evidence using TF-IDF cosine similarity
(local, offline — no pretrained model download needed, consistent with the
project's local-first design). Falls back to word overlap if sklearn is
unavailable.
"""

import re
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from schemas import Claim, Evidence, ClaimStatus, VerificationResult

try:
    from sklearn.feature_extraction.text import TfidfVectorizer
    from sklearn.metrics.pairwise import cosine_similarity
    _HAS_SKLEARN = True
except ImportError:
    _HAS_SKLEARN = False

NUMBER_RE = re.compile(r"\d+(:\d+)?\s*(am|pm)?", re.IGNORECASE)
TIME_RE = re.compile(r"\b\d{1,2}:\d{2}\s*(?:am|pm)?\b", re.IGNORECASE)
ID_RE = re.compile(r"\b\d{3,}\b")  # standalone 3+ digit numbers: shipment IDs, amounts, etc.


def _tokenize(text: str) -> set[str]:
    return set(re.findall(r"[a-z0-9]+", text.lower()))


def _word_overlap_score(a: str, b: str) -> float:
    ta, tb = _tokenize(a), _tokenize(b)
    if not ta:
        return 0.0
    return len(ta & tb) / len(ta)


def relevance_scores(claim_text: str, contents: list[str]) -> list[float]:
    """Score claim_text against each item in contents. Returns one score per item."""
    if not contents:
        return []
    if _HAS_SKLEARN:
        try:
            vectorizer = TfidfVectorizer(stop_words="english")
            matrix = vectorizer.fit_transform([claim_text] + contents)
            sims = cosine_similarity(matrix[0:1], matrix[1:]).flatten()
            return sims.tolist()
        except ValueError:
            pass  # e.g. empty vocabulary after stopword removal -> fall back
    return [_word_overlap_score(claim_text, c) for c in contents]


def _extract_numbers(text: str) -> set[str]:
    return {m.group(0).lower().replace(" ", "") for m in NUMBER_RE.finditer(text)}


def _norm_time(t: str) -> str:
    return t.lower().replace(" ", "")


def _conflicts(claim_text: str, evidence_content: str, relevance: float) -> bool:
    """
    A genuine conflict requires the claim and evidence to be about the SAME
    entity (they share at least one identifying ID number, e.g. a shipment
    ID) but DISAGREE on the TIME associated with it. Extra numbers present
    in one side but not the other (e.g. an amount the claim doesn't mention)
    are not a conflict — only a same-entity, different-time/value situation is.
    """
    if relevance < 0.5:
        return False

    claim_ids = set(ID_RE.findall(claim_text))
    evidence_ids = set(ID_RE.findall(evidence_content))
    shared_ids = claim_ids & evidence_ids
    if not shared_ids:
        return False  # not clearly about the same entity -> not a conflict, just unrelated

    claim_times = {_norm_time(t) for t in TIME_RE.findall(claim_text)}
    evidence_times = {_norm_time(t) for t in TIME_RE.findall(evidence_content)}
    if claim_times and evidence_times and claim_times.isdisjoint(evidence_times):
        return True

    return False


def verify_claim(claim: Claim, evidence_pool: list[Evidence], relevance_threshold: float = 0.2) -> VerificationResult:
    """
    1. Score every evidence item's relevance to the claim (TF-IDF cosine similarity).
    2. No relevant evidence at all -> INSUFFICIENT_EVIDENCE.
    3. Relevant evidence with a conflicting number/time -> CONTRADICTED.
    4. Relevant evidence with high similarity and no conflict -> SUPPORTED.
    5. Weakly relevant, non-conflicting evidence -> UNSUPPORTED.
    """
    if not evidence_pool:
        return VerificationResult(
            claim=claim.model_copy(update={"status": ClaimStatus.INSUFFICIENT_EVIDENCE}),
            status=ClaimStatus.INSUFFICIENT_EVIDENCE,
            reasoning="Evidence pool is empty.",
            relevance_score=0.0,
        )

    contents = [e.content for e in evidence_pool]
    scores = relevance_scores(claim.text, contents)
    scored = list(zip(evidence_pool, scores))
    relevant = [(e, s) for e, s in scored if s >= relevance_threshold]

    if not relevant:
        best = max(scores) if scores else 0.0
        return VerificationResult(
            claim=claim.model_copy(update={"status": ClaimStatus.INSUFFICIENT_EVIDENCE}),
            status=ClaimStatus.INSUFFICIENT_EVIDENCE,
            reasoning="No evidence in the pool is topically relevant to this claim.",
            relevance_score=best,
        )

    conflicting = [(e, s) for e, s in relevant if _conflicts(claim.text, e.content, s)]
    if conflicting:
        support = [e for e, s in relevant if (e, s) not in conflicting]
        conflict_ev = [e for e, s in conflicting]
        updated = claim.model_copy(update={
            "status": ClaimStatus.CONTRADICTED,
            "evidence": support,
            "contradicting_evidence": conflict_ev,
        })
        sources = ", ".join(f"{e.source} (p.{e.page})" for e in conflict_ev)
        return VerificationResult(
            claim=updated, status=ClaimStatus.CONTRADICTED,
            reasoning=f"Relevant evidence disagrees with the claim. Conflicting source(s): {sources}",
            relevance_score=max(s for _, s in conflicting),
        )

    top_score = max(s for _, s in relevant)
    supporting = [e for e, s in relevant if s >= 0.4]
    if supporting:
        updated = claim.model_copy(update={"status": ClaimStatus.SUPPORTED, "evidence": supporting})
        sources = ", ".join(f"{e.source} (p.{e.page})" for e in supporting)
        return VerificationResult(
            claim=updated, status=ClaimStatus.SUPPORTED,
            reasoning=f"Supported by: {sources}", relevance_score=top_score,
        )

    updated = claim.model_copy(update={"status": ClaimStatus.UNSUPPORTED, "evidence": [e for e, s in relevant]})
    return VerificationResult(
        claim=updated, status=ClaimStatus.UNSUPPORTED,
        reasoning="Related evidence exists but does not directly confirm the claim's specific detail.",
        relevance_score=top_score,
    )


if __name__ == "__main__":
    evidence_pool = [
        Evidence(source="incident_report.pdf", page=1, content="Incident occurred at 11:40 AM."),
        Evidence(source="transactions.xlsx", page=1, content="Transaction total: 4821 recorded on 14 September."),
    ]
    print("Using TF-IDF:" , _HAS_SKLEARN)

    r1 = verify_claim(Claim(text="The incident occurred at 11:40 AM."), evidence_pool)
    print(r1.status, round(r1.relevance_score, 3), "-", r1.reasoning)

    r2 = verify_claim(Claim(text="The employee's 2021 salary was 50000."), evidence_pool)
    print(r2.status, round(r2.relevance_score, 3), "-", r2.reasoning)
