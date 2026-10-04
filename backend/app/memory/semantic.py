"""Semantic memory (T12): facts and the entities they are about, across investigations.

Two stores answer one protocol, as the knowledge base does (ADR-010): Neo4j when the graph store is
Neo4j (decision D2), Postgres when it is in memory. **The store is chosen by configuration, never by
availability.** Falling back to Postgres when Neo4j is down would split memory across two stores
and give different answers depending on which was up when a run finished; instead, semantic memory
is unavailable for that run, and the log says so.

Member 4 queried facts by exact subject and predicate. So does `facts()`, on normalised forms, so
`Rahul Sharma` and `rahul  sharma` are one subject and `Arrival Date` and `arrival_date` one
predicate.
"""

from __future__ import annotations

from typing import Protocol

from sqlalchemy import delete, exists, or_, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.session import session_scope
from app.intelligence.knowledge.store import normalize_attribute, normalize_name
from app.models.tables import MemoryEntity, MemoryEntityRun, MemoryFact, MemoryFactSupport
from app.schemas.knowledge import EntityType
from app.schemas.memory import (
    DEFAULT_FACT_LIMIT,
    EntityMemory,
    Fact,
    FactKind,
    FactSupport,
    KnownEntity,
    clamp_limit,
    order_facts,
)


class SemanticMemory(Protocol):
    """Where facts and known entities are kept. Every method may raise; callers contain it."""

    name: str

    async def record(self, entities: list[KnownEntity], facts: list[Fact]) -> None:
        """Merge one run's entities and facts in. Idempotent for the same run."""
        ...

    async def entity(self, name: str) -> EntityMemory | None:
        """An entity across runs, with facts where it is the subject or a relation's object."""
        ...

    async def facts(
        self, subject: str | None = None, predicate: str | None = None, limit: int = 50
    ) -> list[Fact]: ...

    async def forget(self, run_id: str) -> None:
        """Remove what one run contributed; drop facts and entities nothing supports any more."""
        ...


class PostgresSemanticMemory:
    """Semantic memory in Postgres, for when the graph store is in memory."""

    name = "postgres"

    async def record(self, entities: list[KnownEntity], facts: list[Fact]) -> None:
        async with session_scope() as session:
            for entity in entities:
                current = await session.get(MemoryEntity, entity.key)
                if current is None:
                    session.add(
                        MemoryEntity(
                            key=entity.key,
                            name=entity.name,
                            entity_types=[t.value for t in entity.entity_types],
                            aliases=sorted(set(entity.aliases)),
                        )
                    )
                else:
                    types = list(current.entity_types)
                    types += [t.value for t in entity.entity_types if t.value not in types]
                    current.entity_types = types
                    current.aliases = sorted(set(current.aliases) | set(entity.aliases))
                await session.flush()
                for run_id in entity.runs:
                    await session.execute(
                        insert(MemoryEntityRun)
                        .values(key=entity.key, run_id=run_id)
                        .on_conflict_do_nothing()
                    )
            for fact in facts:
                await session.execute(
                    insert(MemoryFact)
                    .values(
                        fact_id=fact.fact_id,
                        kind=fact.kind.value,
                        subject=fact.subject,
                        subject_key=fact.subject_key,
                        predicate=fact.predicate,
                        object=fact.object,
                        object_key=fact.object_key,
                    )
                    .on_conflict_do_nothing()
                )
                for support in fact.support:
                    await session.execute(
                        insert(MemoryFactSupport)
                        .values(fact_id=fact.fact_id, run_id=support.run_id, source=support.source)
                        .on_conflict_do_nothing()
                    )

    async def entity(self, name: str) -> EntityMemory | None:
        key = normalize_name(name)
        if not key:
            return None
        async with session_scope() as session:
            row = await session.get(MemoryEntity, key)
            if row is None:
                return None
            runs = (
                await session.execute(
                    select(MemoryEntityRun.run_id)
                    .where(MemoryEntityRun.key == key)
                    .order_by(MemoryEntityRun.run_id)
                )
            ).scalars()
            known = KnownEntity(
                key=row.key,
                name=row.name,
                entity_types=[EntityType(t) for t in row.entity_types],
                aliases=list(row.aliases),
                runs=list(runs),
            )
            rows = (
                await session.execute(
                    select(MemoryFact).where(
                        or_(
                            MemoryFact.subject_key == key,
                            (MemoryFact.kind == FactKind.RELATION.value)
                            & (MemoryFact.object_key == key),
                        )
                    )
                )
            ).scalars()
            facts = [await _fact(session, r) for r in rows]
        return EntityMemory(entity=known, facts=order_facts(facts))

    async def facts(
        self,
        subject: str | None = None,
        predicate: str | None = None,
        limit: int = DEFAULT_FACT_LIMIT,
    ) -> list[Fact]:
        query = select(MemoryFact)
        if subject:
            query = query.where(MemoryFact.subject_key == normalize_name(subject))
        if predicate:
            query = query.where(MemoryFact.predicate == normalize_attribute(predicate))
        async with session_scope() as session:
            rows = (await session.execute(query)).scalars()
            facts = [await _fact(session, r) for r in rows]
        return order_facts(facts)[: clamp_limit(limit)]

    async def forget(self, run_id: str) -> None:
        async with session_scope() as session:
            await session.execute(
                delete(MemoryFactSupport).where(MemoryFactSupport.run_id == run_id)
            )
            await session.execute(delete(MemoryEntityRun).where(MemoryEntityRun.run_id == run_id))
            await session.execute(
                delete(MemoryFact).where(
                    ~exists().where(MemoryFactSupport.fact_id == MemoryFact.fact_id)
                )
            )
            await session.execute(
                delete(MemoryEntity).where(
                    ~exists().where(MemoryEntityRun.key == MemoryEntity.key),
                    ~exists().where(MemoryFact.subject_key == MemoryEntity.key),
                )
            )


async def _fact(session: AsyncSession, row: MemoryFact) -> Fact:
    support = (
        await session.execute(
            select(MemoryFactSupport.run_id, MemoryFactSupport.source)
            .where(MemoryFactSupport.fact_id == row.fact_id)
            .order_by(MemoryFactSupport.run_id, MemoryFactSupport.source)
        )
    ).all()
    return Fact(
        fact_id=row.fact_id,
        kind=FactKind(row.kind),
        subject=row.subject,
        subject_key=row.subject_key,
        predicate=row.predicate,
        object=row.object,
        object_key=row.object_key,
        support=[FactSupport(run_id=r, source=s) for r, s in support],
    )
