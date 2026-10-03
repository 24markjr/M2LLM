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

`KnowledgeBase` is the protocol. `InMemoryKnowledgeBase` answers from a `KnowledgeSnapshot`;
Phase 29 adds a Neo4j implementation of the same protocol, and the same tests run against both.
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


@runtime_checkable
class KnowledgeBase(Protocol):
    def entities(self) -> list[KnowledgeEntity]: ...
    def find_entity(self, name: str) -> list[KnowledgeEntity]: ...
    def relationships(self, entity_id: str | None = None) -> list[KnowledgeRelationship]: ...
    def claims(self, entity_id: str | None = None) -> list[KnowledgeClaim]: ...
    def claim(self, claim_id: str) -> KnowledgeClaim | None: ...
    def conflicts(self, entity_id: str | None = None) -> list[ClaimConflict]: ...
    def timeline(self, entity_id: str | None = None) -> list[TimelineEvent]: ...
    def compare(self, claim_a: str, claim_b: str) -> ClaimComparison | None: ...
    def network(self, entity_id: str, depth: int = 2) -> EntityNetwork | None: ...
    def investigate(self, name: str) -> EntityInvestigation | None: ...
    def search(self, query: str, depth: int = 1) -> list[SearchHit]: ...


class InMemoryKnowledgeBase:
    """Answers every knowledge question from one run's snapshot. Nothing is shared between runs."""

    def __init__(self, snapshot: KnowledgeSnapshot) -> None:
        self._snapshot = snapshot

    @property
    def snapshot(self) -> KnowledgeSnapshot:
        return self._snapshot

    def entities(self) -> list[KnowledgeEntity]:
        return list(self._snapshot.entities)

    def find_entity(self, name: str) -> list[KnowledgeEntity]:
        """Entities whose name or an alias contains `name`: the original's `LIKE %name%`.

        Ordered best first: an exact match, then the shortest containing name.
        """
        key = normalize_name(name)
        if not key:
            return []

        def spellings(entity: KnowledgeEntity) -> list[str]:
            return [normalize_name(entity.name), *(normalize_name(a) for a in entity.aliases)]

        found = [e for e in self._snapshot.entities if any(key in s for s in spellings(e))]
        return sorted(found, key=lambda e: (key not in spellings(e), len(e.name), e.entity_id))

    def relationships(self, entity_id: str | None = None) -> list[KnowledgeRelationship]:
        return [
            r
            for r in self._snapshot.relationships
            if entity_id is None or entity_id in (r.subject_id, r.object_id)
        ]

    def claims(self, entity_id: str | None = None) -> list[KnowledgeClaim]:
        return [c for c in self._snapshot.claims if entity_id is None or c.entity_id == entity_id]

    def claim(self, claim_id: str) -> KnowledgeClaim | None:
        return next((c for c in self._snapshot.claims if c.claim_id == claim_id), None)

    def conflicts(self, entity_id: str | None = None) -> list[ClaimConflict]:
        return [
            c for c in self._snapshot.conflicts if entity_id is None or c.entity_id == entity_id
        ]

    def timeline(self, entity_id: str | None = None) -> list[TimelineEvent]:
        return build_timeline(self._snapshot.claims, self._snapshot.entities, entity_id=entity_id)

    def compare(self, claim_a: str, claim_b: str) -> ClaimComparison | None:
        first, second = self.claim(claim_a), self.claim(claim_b)
        if first is None or second is None:
            return None
        return compare_claims(first, second)

    def network(self, entity_id: str, depth: int = 2) -> EntityNetwork | None:
        return neighbourhood(
            entity_id,
            min(max(depth, 0), MAX_DEPTH),
            self._snapshot.entities,
            self._snapshot.relationships,
        )

    def investigate(self, name: str) -> EntityInvestigation | None:
        """Everything about the best-matching entity, in one answer."""
        matches = self.find_entity(name)
        if not matches:
            return None
        entity = matches[0]
        network = self.network(entity.entity_id, INVESTIGATION_DEPTH)
        claims = self.claims(entity.entity_id)
        sources = list(dict.fromkeys([*entity.sources, *(c.source for c in claims)]))
        return EntityInvestigation(
            entity=entity,
            sources=sources,
            network=network or EntityNetwork(center_id=entity.entity_id, depth=INVESTIGATION_DEPTH),
            claims=claims,
            conflicts=self.conflicts(entity.entity_id),
        )

    def search(self, query: str, depth: int = 1) -> list[SearchHit]:
        return hybrid_search(
            query,
            self._snapshot.entities,
            self._snapshot.relationships,
            self._snapshot.claims,
            depth=min(max(depth, 0), MAX_DEPTH),
        )
