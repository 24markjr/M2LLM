"""The Neo4j knowledge graph store (Phase 29, ADR-010).

The only module in the application that imports the Neo4j driver (asserted by test). It writes a
run's knowledge base into Neo4j and answers the `KnowledgeBase` protocol from it.

**The graph model.** Every node carries the `run_id` that built it, and every query filters on it,
so one run never reads another's graph (rule 8 of the integration plan; tested with two runs in one
database).

    (:Run {run_id, stats})
    (:Document {run_id, document_id})            (:Run)-[:HAS_DOCUMENT]->(:Document)
    (:Entity {run_id, entity_id, seq, name, key, type, aliases, alias_keys, sources})
    (:Claim {run_id, claim_id, seq, attribute, value, source, document_id, line, quote, grounded})
    (:Conflict {run_id, conflict_id, seq, entity_id, entity_name, attribute, kind, sides})

    (:Entity)-[:MENTIONED_IN {source}]->(:Document)
    (:Entity)-[:RELATES {relationship_id, seq, predicate, source}]->(:Entity)
    (:Entity)-[:HAS_CLAIM]->(:Claim)-[:CITED_IN {source}]->(:Document)
    (:Entity)-[:HAS_CONFLICT]->(:Conflict)<-[:SIDE_OF {value}]-(:Claim)
    (:Claim)-[:CONFLICTS_WITH {conflict_id, attribute, kind}]->(:Claim)

`seq` keeps the order a run produced things in, so a Neo4j read returns the same sequence as the
in-memory store. `key` and `alias_keys` are the normalised names entity lookup matches on.
`CONFLICTS_WITH` links the first claim of each pair of sides, so the graph shows a contradiction as
an edge (the 3D view in Phase 32 draws it).

**What runs in Cypher and what does not.** Storage, listing, lookup by id and name, and the
neighbourhood (a variable-length `RELATES` path) are Cypher. Timeline ordering, search scoring and
the investigation aggregate run on data read from here with the same Python the in-memory store
uses, so the two stores cannot disagree about a score.

**A run's graph is written in one transaction**, after extraction, so nothing ever reads a
half-written graph. Writing a run that already exists replaces it.
"""

from __future__ import annotations

import json
from typing import Any

from neo4j import AsyncDriver, AsyncGraphDatabase, AsyncManagedTransaction

from app.core.logging import get_logger
from app.intelligence.knowledge.base import clamp_depth, investigate, rank_matches
from app.intelligence.knowledge.search import hybrid_search
from app.intelligence.knowledge.store import normalize_name
from app.intelligence.knowledge.timeline import build_timeline, compare_claims
from app.schemas.knowledge import (
    ClaimComparison,
    ClaimConflict,
    ConflictSide,
    EntityInvestigation,
    EntityNetwork,
    ExtractionStats,
    KnowledgeClaim,
    KnowledgeEntity,
    KnowledgeRelationship,
    KnowledgeSnapshot,
    NetworkEdge,
    NetworkNode,
    SearchHit,
    TimelineEvent,
)

log = get_logger(__name__)

# Applied idempotently on first use. Composite uniqueness is available in Community edition; node
# keys (which would also enforce existence) are Enterprise-only, so existence is the writer's job.
SCHEMA = (
    "CREATE CONSTRAINT jarvis_run IF NOT EXISTS FOR (n:Run) REQUIRE n.run_id IS UNIQUE",
    "CREATE CONSTRAINT jarvis_document IF NOT EXISTS "
    "FOR (n:Document) REQUIRE (n.run_id, n.document_id) IS UNIQUE",
    "CREATE CONSTRAINT jarvis_entity IF NOT EXISTS "
    "FOR (n:Entity) REQUIRE (n.run_id, n.entity_id) IS UNIQUE",
    "CREATE CONSTRAINT jarvis_claim IF NOT EXISTS "
    "FOR (n:Claim) REQUIRE (n.run_id, n.claim_id) IS UNIQUE",
    "CREATE CONSTRAINT jarvis_conflict IF NOT EXISTS "
    "FOR (n:Conflict) REQUIRE (n.run_id, n.conflict_id) IS UNIQUE",
    "CREATE INDEX jarvis_entity_key IF NOT EXISTS FOR (n:Entity) ON (n.run_id, n.key)",
)

# Labels a run's graph is made of. Deleting a run removes exactly these, scoped by run_id.
RUN_LABELS = ("Run", "Document", "Entity", "Claim", "Conflict")


def _document_of(source: str) -> str:
    return source.rpartition(":")[0] or source


class Neo4jGraphStore:
    """A connection to Neo4j, and the write and read paths for one run's graph."""

    def __init__(self, driver: AsyncDriver, database: str) -> None:
        self._driver = driver
        self._database = database
        self._schema_ready = False

    @classmethod
    def connect(
        cls, uri: str, user: str, password: str, database: str, *, timeout_s: float = 3.0
    ) -> Neo4jGraphStore:
        driver = AsyncGraphDatabase.driver(uri, auth=(user, password), connection_timeout=timeout_s)
        return cls(driver, database)

    async def available(self) -> bool:
        try:
            await self._driver.verify_connectivity()
        except Exception as exc:  # noqa: BLE001 - any failure to connect means "not available"
            log.info("neo4j_unavailable", error=f"{type(exc).__name__}: {exc}")
            return False
        return True

    async def close(self) -> None:
        await self._driver.close()

    async def ensure_schema(self) -> None:
        if self._schema_ready:
            return
        async with self._driver.session(database=self._database) as session:
            for statement in SCHEMA:
                await session.run(statement)
        self._schema_ready = True

    # --- writing ------------------------------------------------------------------------

    async def save(self, run_id: str, snapshot: KnowledgeSnapshot) -> None:
        """Write one run's graph, replacing any earlier write of the same run. One transaction."""
        await self.ensure_schema()
        async with self._driver.session(database=self._database) as session:
            await session.execute_write(_write_run, run_id, snapshot)
        log.info(
            "knowledge_graph_saved",
            run_id=run_id,
            entities=len(snapshot.entities),
            claims=len(snapshot.claims),
            conflicts=len(snapshot.conflicts),
        )

    async def delete(self, run_id: str) -> None:
        async with self._driver.session(database=self._database) as session:
            await session.execute_write(_delete_run, run_id)

    # --- reading ------------------------------------------------------------------------

    async def read(self, query: str, **params: Any) -> list[dict[str, Any]]:
        async with self._driver.session(database=self._database) as session:
            result = await session.run(query, params)
            return [record.data() for record in [r async for r in result]]

    async def exists(self, run_id: str) -> bool:
        rows = await self.read("MATCH (r:Run {run_id: $r}) RETURN count(r) AS n", r=run_id)
        return bool(rows and rows[0]["n"])

    def base(self, run_id: str) -> Neo4jKnowledgeBase:
        return Neo4jKnowledgeBase(self, run_id)

    async def load(self, run_id: str) -> KnowledgeSnapshot | None:
        """A run's whole knowledge base, read back. None if the run was never written."""
        if not await self.exists(run_id):
            return None
        base = self.base(run_id)
        rows = await self.read("MATCH (r:Run {run_id: $r}) RETURN r.stats AS stats", r=run_id)
        return KnowledgeSnapshot(
            entities=await base.entities(),
            relationships=await base.relationships(),
            claims=await base.claims(),
            conflicts=await base.conflicts(),
            stats=ExtractionStats.model_validate_json(rows[0]["stats"]),
        )


async def _delete_run(tx: AsyncManagedTransaction, run_id: str) -> None:
    for label in RUN_LABELS:
        await tx.run(f"MATCH (n:{label} {{run_id: $r}}) DETACH DELETE n", r=run_id)


async def _write_run(tx: AsyncManagedTransaction, run_id: str, snapshot: KnowledgeSnapshot) -> None:
    await _delete_run(tx, run_id)

    documents = sorted(
        {c.document_id for c in snapshot.claims}
        | {_document_of(s) for e in snapshot.entities for s in e.sources}
        | {_document_of(r.source) for r in snapshot.relationships}
    )
    await tx.run(
        "CREATE (run:Run {run_id: $r, stats: $stats}) "
        "WITH run UNWIND $documents AS doc "
        "CREATE (run)-[:HAS_DOCUMENT]->(:Document {run_id: $r, document_id: doc})",
        r=run_id,
        stats=snapshot.stats.model_dump_json(),
        documents=documents,
    )

    await tx.run(
        "UNWIND $rows AS row "
        "CREATE (e:Entity {run_id: $r, entity_id: row.entity_id, seq: row.seq, name: row.name, "
        "key: row.key, type: row.type, aliases: row.aliases, alias_keys: row.alias_keys, "
        "sources: row.sources}) "
        "WITH e, row UNWIND row.mentions AS mention "
        "MATCH (d:Document {run_id: $r, document_id: mention.document}) "
        "CREATE (e)-[:MENTIONED_IN {source: mention.source}]->(d)",
        r=run_id,
        rows=[
            {
                "entity_id": e.entity_id,
                "seq": i,
                "name": e.name,
                "key": normalize_name(e.name),
                "type": e.entity_type.value,
                "aliases": e.aliases,
                "alias_keys": [normalize_name(a) for a in e.aliases],
                "sources": e.sources,
                "mentions": [{"source": s, "document": _document_of(s)} for s in e.sources],
            }
            for i, e in enumerate(snapshot.entities)
        ],
    )

    await tx.run(
        "UNWIND $rows AS row "
        "MATCH (s:Entity {run_id: $r, entity_id: row.subject_id}) "
        "MATCH (o:Entity {run_id: $r, entity_id: row.object_id}) "
        "CREATE (s)-[:RELATES {relationship_id: row.relationship_id, seq: row.seq, "
        "predicate: row.predicate, source: row.source}]->(o)",
        r=run_id,
        rows=[{**rel.model_dump(), "seq": i} for i, rel in enumerate(snapshot.relationships)],
    )

    await tx.run(
        "UNWIND $rows AS row "
        "MATCH (e:Entity {run_id: $r, entity_id: row.entity_id}) "
        "MATCH (d:Document {run_id: $r, document_id: row.document_id}) "
        "CREATE (c:Claim {run_id: $r, claim_id: row.claim_id, seq: row.seq, "
        "attribute: row.attribute, value: row.value, source: row.source, "
        "document_id: row.document_id, line: row.line, quote: row.quote, grounded: row.grounded}) "
        "CREATE (e)-[:HAS_CLAIM]->(c) "
        "CREATE (c)-[:CITED_IN {source: row.source}]->(d)",
        r=run_id,
        rows=[{**c.model_dump(), "seq": i} for i, c in enumerate(snapshot.claims)],
    )

    for i, conflict in enumerate(snapshot.conflicts):
        await tx.run(
            "MATCH (e:Entity {run_id: $r, entity_id: $entity_id}) "
            "CREATE (k:Conflict {run_id: $r, conflict_id: $conflict_id, seq: $seq, "
            "entity_id: $entity_id, entity_name: $entity_name, attribute: $attribute, "
            "kind: $kind, sides: $sides}) "
            "CREATE (e)-[:HAS_CONFLICT]->(k) "
            "WITH k UNWIND $members AS member "
            "MATCH (c:Claim {run_id: $r, claim_id: member.claim_id}) "
            "CREATE (c)-[:SIDE_OF {value: member.value}]->(k)",
            r=run_id,
            seq=i,
            conflict_id=conflict.conflict_id,
            entity_id=conflict.entity_id,
            entity_name=conflict.entity_name,
            attribute=conflict.attribute,
            kind=conflict.kind.value,
            sides=json.dumps([side.model_dump() for side in conflict.sides]),
            members=[
                {"claim_id": claim_id, "value": side.value}
                for side in conflict.sides
                for claim_id in side.claim_ids
            ],
        )
        heads = [side.claim_ids[0] for side in conflict.sides]
        await tx.run(
            "UNWIND $pairs AS pair "
            "MATCH (a:Claim {run_id: $r, claim_id: pair[0]}) "
            "MATCH (b:Claim {run_id: $r, claim_id: pair[1]}) "
            "CREATE (a)-[:CONFLICTS_WITH {conflict_id: $conflict_id, attribute: $attribute, "
            "kind: $kind}]->(b)",
            r=run_id,
            pairs=[[a, b] for n, a in enumerate(heads) for b in heads[n + 1 :]],
            conflict_id=conflict.conflict_id,
            attribute=conflict.attribute,
            kind=conflict.kind.value,
        )


# --- reading rows back into the typed models -----------------------------------------------


def _entity(row: dict[str, Any]) -> KnowledgeEntity:
    return KnowledgeEntity(
        entity_id=row["entity_id"],
        name=row["name"],
        entity_type=row["type"],
        aliases=list(row.get("aliases") or []),
        sources=list(row.get("sources") or []),
    )


def _claim(row: dict[str, Any]) -> KnowledgeClaim:
    return KnowledgeClaim(
        claim_id=row["claim_id"],
        entity_id=row["entity_id"],
        attribute=row["attribute"],
        value=row["value"],
        source=row["source"],
        document_id=row["document_id"],
        line=row.get("line"),
        quote=row.get("quote") or "",
        grounded=bool(row.get("grounded")),
    )


_ENTITY_FIELDS = (
    "e.entity_id AS entity_id, e.name AS name, e.type AS type, e.aliases AS aliases, "
    "e.sources AS sources"
)
_CLAIM_FIELDS = (
    "c.claim_id AS claim_id, e.entity_id AS entity_id, c.attribute AS attribute, "
    "c.value AS value, c.source AS source, c.document_id AS document_id, c.line AS line, "
    "c.quote AS quote, c.grounded AS grounded"
)


class Neo4jKnowledgeBase:
    """The `KnowledgeBase` protocol, answered from one run's graph in Neo4j."""

    store = "neo4j"

    def __init__(self, graph: Neo4jGraphStore, run_id: str) -> None:
        self._graph = graph
        self._run_id = run_id

    @property
    def run_id(self) -> str:
        return self._run_id

    async def entities(self) -> list[KnowledgeEntity]:
        rows = await self._graph.read(
            f"MATCH (e:Entity {{run_id: $r}}) RETURN {_ENTITY_FIELDS} ORDER BY e.seq",
            r=self._run_id,
        )
        return [_entity(row) for row in rows]

    async def find_entity(self, name: str) -> list[KnowledgeEntity]:
        key = normalize_name(name)
        if not key:
            return []
        rows = await self._graph.read(
            "MATCH (e:Entity {run_id: $r}) "
            "WHERE e.key CONTAINS $k OR any(a IN e.alias_keys WHERE a CONTAINS $k) "
            f"RETURN {_ENTITY_FIELDS} ORDER BY e.seq",
            r=self._run_id,
            k=key,
        )
        # The same ranking as the in-memory store, so both return the same order.
        return rank_matches([_entity(row) for row in rows], name)

    async def relationships(self, entity_id: str | None = None) -> list[KnowledgeRelationship]:
        rows = await self._graph.read(
            "MATCH (s:Entity {run_id: $r})-[x:RELATES]->(o:Entity {run_id: $r}) "
            "WHERE $e IS NULL OR s.entity_id = $e OR o.entity_id = $e "
            "RETURN x.relationship_id AS relationship_id, s.entity_id AS subject_id, "
            "x.predicate AS predicate, o.entity_id AS object_id, x.source AS source "
            "ORDER BY x.seq",
            r=self._run_id,
            e=entity_id,
        )
        return [KnowledgeRelationship.model_validate(row) for row in rows]

    async def claims(self, entity_id: str | None = None) -> list[KnowledgeClaim]:
        rows = await self._graph.read(
            "MATCH (e:Entity {run_id: $r})-[:HAS_CLAIM]->(c:Claim {run_id: $r}) "
            "WHERE $e IS NULL OR e.entity_id = $e "
            f"RETURN {_CLAIM_FIELDS} ORDER BY c.seq",
            r=self._run_id,
            e=entity_id,
        )
        return [_claim(row) for row in rows]

    async def claim(self, claim_id: str) -> KnowledgeClaim | None:
        rows = await self._graph.read(
            "MATCH (e:Entity {run_id: $r})-[:HAS_CLAIM]->(c:Claim {run_id: $r, claim_id: $c}) "
            f"RETURN {_CLAIM_FIELDS}",
            r=self._run_id,
            c=claim_id,
        )
        return _claim(rows[0]) if rows else None

    async def conflicts(self, entity_id: str | None = None) -> list[ClaimConflict]:
        rows = await self._graph.read(
            "MATCH (k:Conflict {run_id: $r}) WHERE $e IS NULL OR k.entity_id = $e "
            "RETURN k.conflict_id AS conflict_id, k.entity_id AS entity_id, "
            "k.entity_name AS entity_name, k.attribute AS attribute, k.kind AS kind, "
            "k.sides AS sides ORDER BY k.seq",
            r=self._run_id,
            e=entity_id,
        )
        return [
            ClaimConflict(
                conflict_id=row["conflict_id"],
                entity_id=row["entity_id"],
                entity_name=row["entity_name"],
                attribute=row["attribute"],
                kind=row["kind"],
                sides=[ConflictSide.model_validate(s) for s in json.loads(row["sides"])],
            )
            for row in rows
        ]

    async def timeline(self, entity_id: str | None = None) -> list[TimelineEvent]:
        return build_timeline(await self.claims(), await self.entities(), entity_id=entity_id)

    async def compare(self, claim_a: str, claim_b: str) -> ClaimComparison | None:
        first, second = await self.claim(claim_a), await self.claim(claim_b)
        if first is None or second is None:
            return None
        return compare_claims(first, second)

    async def network(self, entity_id: str, depth: int = 2) -> EntityNetwork | None:
        """Entities within `depth` hops in either direction: a variable-length Cypher path."""
        hops = clamp_depth(depth)
        # A path length cannot be a query parameter in Cypher, so it is formatted in. It is an
        # int, clamped to 0..MAX_DEPTH above, so nothing from the caller reaches the query text.
        reach = (
            f"OPTIONAL MATCH (c)-[:RELATES*1..{hops}]-(n:Entity {{run_id: $r}}) "
            "WITH c, collect(DISTINCT n) AS found "
            if hops
            else "WITH c, [] AS found "
        )
        rows = await self._graph.read(
            "MATCH (c:Entity {run_id: $r, entity_id: $id}) " + reach + "UNWIND [c] + found AS e "
            "WITH DISTINCT e "
            f"RETURN {_ENTITY_FIELDS} ORDER BY e.seq",
            r=self._run_id,
            id=entity_id,
        )
        if not rows:
            return None
        reached = [_entity(row) for row in rows]
        ids = [e.entity_id for e in reached]
        edges = await self._graph.read(
            "MATCH (s:Entity {run_id: $r})-[x:RELATES]->(o:Entity {run_id: $r}) "
            "WHERE s.entity_id IN $ids AND o.entity_id IN $ids "
            "RETURN s.entity_id AS from_id, o.entity_id AS to_id, x.predicate AS predicate, "
            "x.source AS source ORDER BY x.seq",
            r=self._run_id,
            ids=ids,
        )
        return EntityNetwork(
            center_id=entity_id,
            depth=hops,
            nodes=[
                NetworkNode(entity_id=e.entity_id, name=e.name, entity_type=e.entity_type)
                for e in reached
            ],
            edges=[NetworkEdge.model_validate(edge) for edge in edges],
        )

    async def investigate(self, name: str) -> EntityInvestigation | None:
        return await investigate(self, name)

    async def search(self, query: str, depth: int = 1) -> list[SearchHit]:
        return hybrid_search(
            query,
            await self.entities(),
            await self.relationships(),
            await self.claims(),
            depth=clamp_depth(depth),
        )
