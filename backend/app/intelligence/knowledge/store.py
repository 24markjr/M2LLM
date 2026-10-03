"""Entity resolution and the run's knowledge accumulator (K2-K4).

Ported from Member 3's `resolve.py` and `db.py`. What is kept:

- **Resolution by name.** The same name means the same entity across every document of the run.
- **Relationships need both ends.** A relationship whose subject or object is not a known entity is
  skipped "rather than store garbage", as the original put it. Skipped ones are counted.
- **Every mention is recorded** (the original's `entity_sources` table), here as citations.

What changed, each because of a defect in the original:

- **Names.** `LOWER(name)` became casefold with punctuation removed, whitespace collapsed and a
  leading "the" dropped. "Shipment #4821" and "shipment 4821" were two entities.
- **Claims about unextracted entities.** The original stored the raw name as the entity; the entity
  is now created (type `OTHER`). One entity was split across an id and a string.
- **Relationship endpoints** are looked up across the whole run, not the same chunk only. An entity
  introduced in one paragraph and related in the next was dropped.
- **One accumulator per run**, discarded after, instead of one global SQLite file. A later
  investigation saw an earlier one's claims.
- **Sequential ids** (`ENT-001`) instead of random ones, so a run's knowledge base is reproducible.
"""

from __future__ import annotations

import re

from app.schemas.knowledge import (
    EntityType,
    ExtractionStats,
    KnowledgeClaim,
    KnowledgeEntity,
    KnowledgeRelationship,
    KnowledgeSnapshot,
)

_PUNCTUATION = re.compile(r"[^\w\s]")
_SPACES = re.compile(r"\s+")
_ATTRIBUTE = re.compile(r"[^a-z0-9]+")


def normalize_name(name: str) -> str:
    """The resolution key for an entity name."""
    key = _SPACES.sub(" ", _PUNCTUATION.sub(" ", name.casefold())).strip()
    return key[4:] if key.startswith("the ") else key


def normalize_attribute(attribute: str) -> str:
    """`Arrival Date`, `arrival-date` and `arrival_date` are one attribute."""
    return _ATTRIBUTE.sub("_", attribute.casefold()).strip("_")


def entity_type(raw: str) -> EntityType:
    candidate = raw.strip().upper()
    aliases = {"ORGANIZATION": "ORG", "ORGANISATION": "ORG", "COMPANY": "ORG", "PLACE": "LOCATION"}
    candidate = aliases.get(candidate, candidate)
    try:
        return EntityType(candidate)
    except ValueError:
        return EntityType.OTHER


class KnowledgeAccumulator:
    """Collects one run's entities, relationships and claims, resolving names as it goes."""

    def __init__(self, *, max_claims: int) -> None:
        self._max_claims = max_claims
        self._entities: dict[str, KnowledgeEntity] = {}
        self._by_key: dict[str, str] = {}
        self._relationships: list[KnowledgeRelationship] = []
        self._claims: list[KnowledgeClaim] = []
        self._claim_keys: set[tuple[str, str, str, str]] = set()
        self.stats = ExtractionStats()

    # --- entities ------------------------------------------------------------------

    def resolve(self, name: str) -> str | None:
        """The id of a known entity with this name, or None."""
        return self._by_key.get(normalize_name(name))

    def entity(
        self, name: str, raw_type: str = "OTHER", source: str = ""
    ) -> KnowledgeEntity | None:
        """Find or create the entity for `name`, recording the mention. None for an empty name."""
        key = normalize_name(name)
        if not key:
            return None
        existing = self._by_key.get(key)
        if existing is None:
            created = KnowledgeEntity(
                entity_id=f"ENT-{len(self._entities) + 1:03d}",
                name=name.strip(),
                entity_type=entity_type(raw_type),
            )
            self._entities[created.entity_id] = created
            self._by_key[key] = created.entity_id
            existing = created.entity_id

        found = self._entities[existing]
        spelled = name.strip()
        if spelled != found.name and spelled not in found.aliases:
            found.aliases.append(spelled)
        # A specific type learned later replaces OTHER; it never overwrites a specific one.
        if found.entity_type is EntityType.OTHER:
            found.entity_type = entity_type(raw_type)
        if source and source not in found.sources:
            found.sources.append(source)
        return found

    @property
    def entity_names(self) -> list[str]:
        return [e.name for e in self._entities.values()]

    # --- relationships and claims ----------------------------------------------------

    def relationship(self, subject: str, predicate: str, obj: str, source: str) -> None:
        subject_id, object_id = self.resolve(subject), self.resolve(obj)
        predicate_name = normalize_attribute(predicate)
        if not subject_id or not object_id or not predicate_name:
            self.stats.relationships_skipped += 1
            return
        self._relationships.append(
            KnowledgeRelationship(
                relationship_id=f"REL-{len(self._relationships) + 1:03d}",
                subject_id=subject_id,
                predicate=predicate_name,
                object_id=object_id,
                source=source,
            )
        )

    def claim(
        self,
        *,
        entity_name: str,
        attribute: str,
        value: str,
        source: str,
        document_id: str,
        line: int | None,
        quote: str,
        grounded: bool,
    ) -> None:
        attribute_name = normalize_attribute(attribute)
        if not attribute_name or not value.strip():
            return
        found = self.entity(entity_name, source=source)
        if found is None:
            return
        key = (found.entity_id, attribute_name, " ".join(value.casefold().split()), source)
        if key in self._claim_keys:
            self.stats.duplicate_claims += 1
            return
        if len(self._claims) >= self._max_claims:
            self.stats.claims_capped += 1
            return
        self._claim_keys.add(key)
        self._claims.append(
            KnowledgeClaim(
                claim_id=f"CLM-{len(self._claims) + 1:03d}",
                entity_id=found.entity_id,
                attribute=attribute_name,
                value=value.strip(),
                source=source,
                document_id=document_id,
                line=line,
                quote=quote.strip()[:300],
                grounded=grounded,
            )
        )
        self.stats.claims += 1
        if not grounded:
            self.stats.ungrounded_claims += 1

    @property
    def attribute_names(self) -> list[str]:
        """Attribute names used so far, most frequent first."""
        counts: dict[str, int] = {}
        for claim in self._claims:
            counts[claim.attribute] = counts.get(claim.attribute, 0) + 1
        return sorted(counts, key=lambda a: (-counts[a], a))

    # --- result ----------------------------------------------------------------------

    def snapshot(self) -> KnowledgeSnapshot:
        """The run's knowledge base. Conflicts are computed separately, from these claims."""
        return KnowledgeSnapshot(
            entities=list(self._entities.values()),
            relationships=list(self._relationships),
            claims=list(self._claims),
            stats=self.stats.model_copy(),
        )
