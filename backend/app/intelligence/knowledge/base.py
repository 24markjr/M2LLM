"""One query surface over a run's knowledge (K2-K11).

Every question Member 3's REST API answered, as typed methods:

| Original endpoint | Method |
|---|---|
| `/entities` | `entities()` |
| `/find_entity?name=` | `find_entity(name)` |
| `/relationships`, `/relationships/{id}` | `relationships(entity_id=None)` |
| `/claims` | `claims(entity_id=None)` |
| `/contradictions` | `conflicts(entity_id=None)` |
| `/timeline`, `/entity/{id}/timeline` | `timeline(entity_id=None)` |
| `/timeline/compare` | `compare(claim_a, claim_b)` |
| `/entity/{id}/network?depth=` | `network(entity_id, depth)` |
| `/evidence/{claim_id}` | `claim(claim_id)` |
| `/investigation/{name}` | `investigate(name)` |
| `/search?q=&depth=` | `search(query, depth)` |

`KnowledgeBase` is the protocol, and it is **async** (Phase 29): the Neo4j implementation in
`app/integrations/neo4j_store.py` answers over the network, and both implementations share one
interface so a caller never knows which it has. `InMemoryKnowledgeBase` answers from a snapshot and
is the fallback when Neo4j cannot be reached. The same test suite runs against both.

The analysis itself (timeline order, search scores, the investigation aggregate, entity ranking)
is shared code, not reimplemented per store. Two stores computing a search score two ways would
eventually disagree, and nothing would say which was right.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from app.intelligence.knowledge.graph import neighbourhood
from app.intelligence.knowledge.search import hybrid_search
from app.intelligence.knowledge.store import normalize_name
from app.intelligence.knowledge.timeline import build_timeline, compare_claims
from app.schemas.knowledge import (
    ClaimComparison,
    ClaimConflict,
    EntityInvestigation,
    EntityNetwork,
    KnowledgeClaim,
    KnowledgeEntity,
    KnowledgeRelationship,
    KnowledgeSnapshot,
    SearchHit,
    TimelineEvent,
)

# The original's default depth for an investigation's network.
INVESTIGATION_DEPTH = 2
# Deeper than this, a neighbourhood is most of the graph and stops being an answer.
MAX_DEPTH = 4


def clamp_depth(depth: int) -> int:
    return min(max(depth, 0), MAX_DEPTH)


@runtime_checkable
class KnowledgeBase(Protocol):
    """A run's knowledge, whichever store holds it."""

    @property
    def store(self) -> str: ...
    async def entities(self) -> list[KnowledgeEntity]: ...
    async def find_entity(self, name: str) -> list[KnowledgeEntity]: ...
    async def relationships(self, entity_id: str | None = None) -> list[KnowledgeRelationship]: ...
    async def claims(self, entity_id: str | None = None) -> list[KnowledgeClaim]: ...
    async def claim(self, claim_id: str) -> KnowledgeClaim | None: ...
    async def conflicts(self, entity_id: str | None = None) -> list[ClaimConflict]: ...
    async def timeline(self, entity_id: str | None = None) -> list[TimelineEvent]: ...
    async def compare(self, claim_a: str, claim_b: str) -> ClaimComparison | None: ...
    async def network(self, entity_id: str, depth: int = 2) -> EntityNetwork | None: ...
    async def investigate(self, name: str) -> EntityInvestigation | None: ...
    async def search(self, query: str, depth: int = 1) -> list[SearchHit]: ...


# --- shared analysis -------------------------------------------------------------------


def rank_matches(entities: list[KnowledgeEntity], name: str) -> list[KnowledgeEntity]:
    """Entities whose name or an alias contains `name`: the original's `LIKE %name%`.

    Ordered best first: an exact match, then the shortest containing name.
    """
    key = normalize_name(name)
    if not key:
        return []

    def spellings(entity: KnowledgeEntity) -> list[str]:
        return [normalize_name(entity.name), *(normalize_name(a) for a in entity.aliases)]

    found = [e for e in entities if any(key in s for s in spellings(e))]
    return sorted(found, key=lambda e: (key not in spellings(e), len(e.name), e.entity_id))


async def investigate(base: KnowledgeBase, name: str) -> EntityInvestigation | None:
    """Everything about the best-matching entity, in one answer: Member 3's main endpoint."""
    matches = await base.find_entity(name)
    if not matches:
        return None
    entity = matches[0]
    network = await base.network(entity.entity_id, INVESTIGATION_DEPTH)
    claims = await base.claims(entity.entity_id)
    sources = list(dict.fromkeys([*entity.sources, *(c.source for c in claims)]))
    return EntityInvestigation(
        entity=entity,
        sources=sources,
        network=network or EntityNetwork(center_id=entity.entity_id, depth=INVESTIGATION_DEPTH),
        claims=claims,
        conflicts=await base.conflicts(entity.entity_id),
    )


# --- the in-memory store ------------------------------------------------------------------


class InMemoryKnowledgeBase:
    """Answers every knowledge question from one run's snapshot. Nothing is shared between runs."""

    store = "memory"

    def __init__(self, snapshot: KnowledgeSnapshot) -> None:
        self._snapshot = snapshot

    @property
    def snapshot(self) -> KnowledgeSnapshot:
        return self._snapshot

    async def entities(self) -> list[KnowledgeEntity]:
        return list(self._snapshot.entities)

    async def find_entity(self, name: str) -> list[KnowledgeEntity]:
        return rank_matches(self._snapshot.entities, name)

    async def relationships(self, entity_id: str | None = None) -> list[KnowledgeRelationship]:
        return [
            r
            for r in self._snapshot.relationships
            if entity_id is None or entity_id in (r.subject_id, r.object_id)
        ]

    async def claims(self, entity_id: str | None = None) -> list[KnowledgeClaim]:
        return [c for c in self._snapshot.claims if entity_id is None or c.entity_id == entity_id]

    async def claim(self, claim_id: str) -> KnowledgeClaim | None:
        return next((c for c in self._snapshot.claims if c.claim_id == claim_id), None)

    async def conflicts(self, entity_id: str | None = None) -> list[ClaimConflict]:
        return [
            c for c in self._snapshot.conflicts if entity_id is None or c.entity_id == entity_id
        ]

    async def timeline(self, entity_id: str | None = None) -> list[TimelineEvent]:
        return build_timeline(self._snapshot.claims, self._snapshot.entities, entity_id=entity_id)

    async def compare(self, claim_a: str, claim_b: str) -> ClaimComparison | None:
        first, second = await self.claim(claim_a), await self.claim(claim_b)
        if first is None or second is None:
            return None
        return compare_claims(first, second)

    async def network(self, entity_id: str, depth: int = 2) -> EntityNetwork | None:
        return neighbourhood(
            entity_id, clamp_depth(depth), self._snapshot.entities, self._snapshot.relationships
        )

    async def investigate(self, name: str) -> EntityInvestigation | None:
        return await investigate(self, name)

    async def search(self, query: str, depth: int = 1) -> list[SearchHit]:
        return hybrid_search(
            query,
            self._snapshot.entities,
            self._snapshot.relationships,
            self._snapshot.claims,
            depth=clamp_depth(depth),
        )
