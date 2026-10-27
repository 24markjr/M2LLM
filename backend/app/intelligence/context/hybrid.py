"""Hybrid search: keywords beside meaning (v4 Phase 2).

Stored retrieval searched by meaning alone. Meaning is what an embedding is bad at for the things an
investigation most often searches for - an invoice number, a host name, an account: `INV-1042` and
`INV-1024` are neighbours in meaning and different facts. So a workspace is also searched by its
words (BM25 in memory, Postgres full-text search in the database), and the two rankings are merged
by reciprocal rank fusion: each passage scores the sum of 1 / (60 + its rank) in each list, the
constant from Cormack et al. (2009). Fusion needs no tuning between two scales that do not compare.
"""

from __future__ import annotations

import math
import re
from collections import Counter

from app.intelligence.context.manager import RetrievedChunk

RRF_K = 60
_TOKEN = re.compile(r"[a-z0-9][a-z0-9_.-]*[a-z0-9]|[a-z0-9]")
_STOP = frozenset(
    "a an and are as at be by for from has have in is it its of on or that the this to was were "
    "what when where which who with did does do how why".split()
)


def terms(text: str) -> list[str]:
    """The words a passage is searched by: lower-case, identifiers kept whole (`inv-1042`)."""
    return [t for t in _TOKEN.findall(text.lower()) if t not in _STOP]


def bm25(
    query: str, passages: list[RetrievedChunk], *, k1: float = 1.5, b: float = 0.75
) -> list[RetrievedChunk]:
    """Okapi BM25 over the given passages; only passages sharing a query term, best first, each
    scored relative to the best (so 1.0 is the strongest keyword match)."""
    wanted = set(terms(query))
    if not wanted or not passages:
        return []
    docs = [Counter(terms(p.chunk.text)) for p in passages]
    average = sum(sum(d.values()) for d in docs) / len(docs) or 1.0
    frequency = {t: sum(1 for d in docs if t in d) for t in wanted}
    scored: list[tuple[float, RetrievedChunk]] = []
    for doc, passage in zip(docs, passages, strict=True):
        length = sum(doc.values())
        score = 0.0
        for term in wanted:
            if term not in doc:
                continue
            idf = math.log(1 + (len(docs) - frequency[term] + 0.5) / (frequency[term] + 0.5))
            tf = doc[term]
            score += idf * tf * (k1 + 1) / (tf + k1 * (1 - b + b * length / average))
        if score > 0:
            scored.append((score, passage))
    scored.sort(key=lambda pair: (-pair[0], pair[1].chunk.chunk_id))
    best = scored[0][0] if scored else 1.0
    return [p.model_copy(update={"score": round(s / best, 4)}) for s, p in scored]


def fuse(rankings: list[list[RetrievedChunk]], limit: int) -> list[RetrievedChunk]:
    """Reciprocal rank fusion of several best-first lists. A passage keeps its first-seen score
    (meaning's similarity when it has one); the order is the fused one."""
    fused: dict[str, float] = {}
    first: dict[str, RetrievedChunk] = {}
    for ranking in rankings:
        for rank, hit in enumerate(ranking, start=1):
            key = hit.chunk.chunk_id
            fused[key] = fused.get(key, 0.0) + 1.0 / (RRF_K + rank)
            first.setdefault(key, hit)
    order = sorted(fused, key=lambda key: (-fused[key], key))
    return [first[key] for key in order[:limit]]
