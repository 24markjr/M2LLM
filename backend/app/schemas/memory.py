"""Memory across investigations (Phase 33): Member 4's three tiers, fitted to JARVIS.

- **Working (T10).** Member 4: a mutable `WorkingMemory` filled during a run. Here:
  `WorkingMemorySnapshot`, derived from a finished `MissionResult`, so it cannot drift from the
  task graph.
- **Episodic (T11).** Member 4: a SQLite Q&A log and archived snapshots. Here: `Episode` (one per
  finding, any status) and `ArchivedInvestigation`, in Postgres.
- **Semantic (T12).** Member 4: SQLite subject-predicate-object facts with `confidence=1.0`. Here:
  `Fact`s between `KnownEntity`s merged across runs, in Neo4j (or Postgres), with no confidence -
  `support` says which runs asserted each, and from which lines.

**Memory is for people to search. It is never read back into a run** (invariant 4): a run that
used an earlier run's facts could not be reconstructed from its own events. See
`.claude/architecture/memory.md`.
"""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum

from pydantic import Field

from app.schemas.common import JarvisModel, NonEmptyStr, utcnow
from app.schemas.knowledge import EntityType

# --- working (T10) -----------------------------------------------------------------------------


class WorkingMemorySnapshot(JarvisModel):
    """What a run had in mind when it finished: Member 4's `snapshot()`, read off the result.

    Member 4 reduced evidence to a count in the snapshot; so does this.
    """

    investigation_id: str
    objective: str
    plan_steps: list[str] = Field(default_factory=list)
    evidence_count: int = Field(default=0, ge=0)
    hypotheses: list[str] = Field(default_factory=list)
    findings: list[str] = Field(default_factory=list)
    started_at: datetime | None = None


# --- episodic (T11) ----------------------------------------------------------------------------


class Episode(JarvisModel):
    """One finding of one run, as Member 4 logged one question and answer.

    Every finding is logged with its verification status, rejected ones included: a memory of
    only what passed would make past investigations look better than they were.
    """

    episode_id: str
    run_id: str
    objective: str
    claim: str
    sources: list[str] = Field(default_factory=list)
    verification_status: str = ""
    created_at: datetime = Field(default_factory=utcnow)


class ArchivedInvestigation(JarvisModel):
    run_id: str
    objective: str
    snapshot: WorkingMemorySnapshot
    archived_at: datetime = Field(default_factory=utcnow)


# --- semantic (T12) ----------------------------------------------------------------------------


class FactKind(StrEnum):
    # `entity attribute = value`, from a knowledge claim.
    ATTRIBUTE = "ATTRIBUTE"
    # `entity predicate other-entity`, from a knowledge relationship.
    RELATION = "RELATION"


class FactSupport(JarvisModel):
    """One run's citation of a fact: which investigation, and which line it read it from."""

    run_id: str
    source: str


class Fact(JarvisModel):
    """A subject-predicate-object fact, as Member 4 stored one, without the asserted confidence.

    Member 4 stored `confidence=1.0` for every fact. Here a fact carries its support instead,
    and `support_count` is how many distinct (run, source line) pairs asserted it, so a reader can
    judge it rather than be told.
    """

    fact_id: str
    kind: FactKind
    subject: NonEmptyStr
    subject_key: str
    predicate: NonEmptyStr
    object: NonEmptyStr
    # Normalised object: an entity key for a relation, the folded value for an attribute.
    object_key: str
    support: list[FactSupport] = Field(default_factory=list)

    # Plain properties, not `@computed_field`: a computed field is written into the JSON, and with
    # `extra="forbid"` the model would reject its own output (schemas.md, decision 5). The API
    # returns them through `FactView`.
    @property
    def support_count(self) -> int:
        return len({(s.run_id, s.source) for s in self.support})

    @property
    def runs(self) -> list[str]:
        return sorted({s.run_id for s in self.support})


class FactView(JarvisModel):
    """A fact as the API returns it, with its support count and runs as plain fields."""

    fact_id: str
    kind: FactKind
    subject: str
    predicate: str
    object: str
    support: list[FactSupport] = Field(default_factory=list)
    support_count: int = Field(ge=0)
    runs: list[str] = Field(default_factory=list)

    @classmethod
    def of(cls, fact: Fact) -> FactView:
        return cls(
            fact_id=fact.fact_id,
            kind=fact.kind,
            subject=fact.subject,
            predicate=fact.predicate,
            object=fact.object,
            support=list(fact.support),
            support_count=fact.support_count,
            runs=fact.runs,
        )


class KnownEntity(JarvisModel):
    """An entity as seen across investigations, merged by normalised name."""

    key: str
    name: str
    entity_types: list[EntityType] = Field(default_factory=list)
    aliases: list[str] = Field(default_factory=list)
    runs: list[str] = Field(default_factory=list)


class EntityMemory(JarvisModel):
    """An entity across past investigations, with the facts known about it."""

    entity: KnownEntity
    facts: list[Fact] = Field(default_factory=list)


class EntityMemoryView(JarvisModel):
    """`EntityMemory` as the API returns it."""

    entity: KnownEntity
    facts: list[FactView] = Field(default_factory=list)

    @classmethod
    def of(cls, memory: EntityMemory) -> EntityMemoryView:
        return cls(entity=memory.entity, facts=[FactView.of(f) for f in memory.facts])


class MemoryRecord(JarvisModel):
    """Everything one finished run contributes to memory. Built without touching any store."""

    run_id: str
    investigation: ArchivedInvestigation
    episodes: list[Episode] = Field(default_factory=list)
    entities: list[KnownEntity] = Field(default_factory=list)
    facts: list[Fact] = Field(default_factory=list)


# --- shared by both semantic stores, so they list facts identically ------------------------

DEFAULT_FACT_LIMIT = 50
MAX_FACT_LIMIT = 200


def clamp_limit(limit: int) -> int:
    return max(1, min(limit, MAX_FACT_LIMIT))


def order_facts(facts: list[Fact]) -> list[Fact]:
    """Best supported first, then by statement, so both stores list facts in the same order."""
    return sorted(facts, key=lambda f: (-f.support_count, f.subject_key, f.predicate, f.object))
