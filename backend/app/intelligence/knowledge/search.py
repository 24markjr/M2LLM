"""Explainable hybrid search over a run's claims (K9).

Ported from Member 3's `retrieval.py`. The score is the original's, point for point, and every
point carries its reason, so no result has an unexplained number:

| Points | Reason |
|---|---|
| +3 | "direct entity match": the claim is about an entity whose name contains a query word |
| +1 | "connected via graph": the claim is about an entity within `depth` hops of one |
| +1 per word | "keyword match: ...": query words that appear in the claim's attribute or value |
| +1 | "has source document" |

Query words of fewer than three characters do not match entity names, as in the original.

**One fix.** The original added the last point to every claim, and every claim has a source, so
every claim scored at least 1 and search returned the entire knowledge base. The point is now only
added to a claim that matched something else.
"""

from __future__ import annotations

import re

from app.intelligence.knowledge.graph import neighbourhood
from app.intelligence.knowledge.store import normalize_name
from app.schemas.knowledge import (
    KnowledgeClaim,
    KnowledgeEntity,
    KnowledgeRelationship,
    SearchHit,
)

_WORD = re.compile(r"[a-z0-9]+")
MIN_ENTITY_WORD = 3


def _words(text: str) -> set[str]:
    return set(_WORD.findall(text.lower()))


def hybrid_search(
    query: str,
    entities: list[KnowledgeEntity],
    relationships: list[KnowledgeRelationship],
    claims: list[KnowledgeClaim],
    *,
    depth: int = 1,
) -> list[SearchHit]:
    words = _words(query)
    names = {e.entity_id: e.name for e in entities}

    # 1. Entities whose name (or an alias) contains a significant query word.
    matched: set[str] = set()
    for entity in entities:
        spellings = [normalize_name(entity.name), *(normalize_name(a) for a in entity.aliases)]
        for word in words:
            if len(word) >= MIN_ENTITY_WORD and any(word in s for s in spellings):
                matched.add(entity.entity_id)
                break

    # 2. Entities connected to those through the graph.
    related = set(matched)
    for entity_id in matched:
        network = neighbourhood(entity_id, depth, entities, relationships)
        if network is not None:
            related.update(node.entity_id for node in network.nodes)

    # 3. Score every claim, with a reason for every point.
    hits: list[SearchHit] = []
    for claim in claims:
        score = 0
        reasons: list[str] = []
        if claim.entity_id in matched:
            score += 3
            reasons.append("direct entity match")
        elif claim.entity_id in related:
            score += 1
            reasons.append("connected via graph")

        overlap = sorted(words & _words(f"{claim.attribute} {claim.value}"))
        if overlap:
            score += len(overlap)
            reasons.append(f"keyword match: {', '.join(overlap)}")

        if score > 0 and claim.source:
            score += 1
            reasons.append("has source document")

        if score > 0:
            hits.append(
                SearchHit(
                    claim=claim,
                    entity_name=names.get(claim.entity_id, ""),
                    score=score,
                    explanation=reasons,
                )
            )

    hits.sort(key=lambda hit: (-hit.score, hit.claim.claim_id))
    return hits
