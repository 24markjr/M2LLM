"""Phase 29: the knowledge query surface, against both stores.

Every protocol test runs twice: on `InMemoryKnowledgeBase` and on the Neo4j store. The Neo4j run
skips when Neo4j is not reachable, which is right on a laptop with Docker stopped. In CI the
integration job starts a Neo4j service and fails if this file skips (`.github/workflows/ci.yml`),
because a silently skipped store test is a green tick over nothing.

Holding both stores to one suite is the point: the in-memory store is the fallback a run gets when
Neo4j is down, and a fallback that answers differently would change what a run reports depending
on whether a container was up.
"""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator, Iterator

import pytest

from app.core.config import GraphStoreName, get_settings
from app.integrations import graph_store
from app.integrations.neo4j_store import Neo4jGraphStore
from app.intelligence.knowledge.base import MAX_DEPTH, InMemoryKnowledgeBase, KnowledgeBase
from app.intelligence.knowledge.conflicts import detect_conflicts
from app.schemas.knowledge import (
    ClaimOrder,
    EntityType,
    ExtractionStats,
    KnowledgeClaim,
    KnowledgeEntity,
    KnowledgeRelationship,
    KnowledgeSnapshot,
)

ENTITIES = [
    KnowledgeEntity(
        entity_id="ENT-001",
        name="Shipment 4821",
        entity_type=EntityType.SHIPMENT,
        aliases=["Shipment #4821"],
        sources=["a.txt:r1"],
    ),
    KnowledgeEntity(
        entity_id="ENT-002",
        name="Rahul Sharma",
        entity_type=EntityType.PERSON,
        sources=["c.txt:r1"],
    ),
    KnowledgeEntity(
        entity_id="ENT-003", name="ABC Logistics", entity_type=EntityType.ORG, sources=["c.txt:r1"]
    ),
    KnowledgeEntity(
        entity_id="ENT-004",
        name="Mumbai warehouse",
        entity_type=EntityType.LOCATION,
        sources=["a.txt:r1"],
    ),
]
RELATIONSHIPS = [
    KnowledgeRelationship(
        relationship_id="REL-001",
        subject_id="ENT-002",
        predicate="works_for",
        object_id="ENT-003",
        source="c.txt:r1",
    ),
    KnowledgeRelationship(
        relationship_id="REL-002",
        subject_id="ENT-002",
        predicate="present_at",
        object_id="ENT-004",
        source="d.txt:r1",
    ),
    KnowledgeRelationship(
        relationship_id="REL-003",
        subject_id="ENT-001",
        predicate="arrived_at",
        object_id="ENT-004",
        source="a.txt:r1",
    ),
]


def _claim(n: int, entity: str, attribute: str, value: str, source: str) -> KnowledgeClaim:
    return KnowledgeClaim(
        claim_id=f"CLM-{n:03d}",
        entity_id=entity,
        attribute=attribute,
        value=value,
        source=source,
        document_id=source.split(":")[0],
        line=1,
        quote=f"line with {value}",
    )


CLAIMS = [
    _claim(1, "ENT-001", "arrival_date", "14 September", "a.txt:r1"),
    _claim(2, "ENT-001", "arrival_date", "16 September", "b.txt:r1"),
    _claim(3, "ENT-002", "works_for", "ABC Logistics", "c.txt:r1"),
    _claim(4, "ENT-002", "present_at", "Mumbai warehouse", "d.txt:r1"),
]
SNAPSHOT = KnowledgeSnapshot(
    entities=ENTITIES,
    relationships=RELATIONSHIPS,
    claims=CLAIMS,
    conflicts=detect_conflicts(CLAIMS, ENTITIES),
    stats=ExtractionStats(documents=4, chunks=4, llm_calls=4, claims=4),
)


async def _neo4j() -> Neo4jGraphStore:
    settings = get_settings()
    store = Neo4jGraphStore.connect(
        settings.neo4j_uri, settings.neo4j_user, settings.neo4j_password, settings.neo4j_database
    )
    if not await store.available():
        await store.close()
        pytest.skip("Neo4j not reachable: start it with `docker compose up -d neo4j`")
    return store


@pytest.fixture(params=["memory", "neo4j"])
async def base(request: pytest.FixtureRequest) -> AsyncIterator[KnowledgeBase]:
    if request.param == "memory":
        yield InMemoryKnowledgeBase(SNAPSHOT)
        return
    store = await _neo4j()
    run_id = f"run_{uuid.uuid4().hex[:12]}"
    await store.save(run_id, SNAPSHOT)
    try:
        yield store.base(run_id)
    finally:
        await store.delete(run_id)
        await store.close()


# --- the protocol, on both stores ----------------------------------------------------------


async def test_the_store_satisfies_the_protocol(base: KnowledgeBase) -> None:
    assert isinstance(base, KnowledgeBase)
    assert base.store in {"memory", "neo4j"}


async def test_entities_relationships_and_claims_come_back_whole_and_in_order(
    base: KnowledgeBase,
) -> None:
    assert await base.entities() == ENTITIES
    assert await base.relationships() == RELATIONSHIPS
    assert await base.claims() == CLAIMS
    assert [r.relationship_id for r in await base.relationships("ENT-004")] == [
        "REL-002",
        "REL-003",
    ]
    assert [c.claim_id for c in await base.claims("ENT-001")] == ["CLM-001", "CLM-002"]


async def test_claim_lookup(base: KnowledgeBase) -> None:
    assert await base.claim("CLM-003") == CLAIMS[2]
    assert await base.claim("CLM-999") is None


async def test_find_entity_matches_aliases_and_ranks_the_exact_match_first(
    base: KnowledgeBase,
) -> None:
    assert [e.name for e in await base.find_entity("shipment #4821")] == ["Shipment 4821"]
    assert [e.name for e in await base.find_entity("mumbai")] == ["Mumbai warehouse"]
    assert await base.find_entity("") == []
    assert await base.find_entity("nobody at all") == []


async def test_conflicts_round_trip_with_every_side(base: KnowledgeBase) -> None:
    assert await base.conflicts() == SNAPSHOT.conflicts
    [conflict] = await base.conflicts("ENT-001")
    assert [(s.value, s.sources) for s in conflict.sides] == [
        ("14 September", ["a.txt:r1"]),
        ("16 September", ["b.txt:r1"]),
    ]
    assert await base.conflicts("ENT-002") == []


async def test_timeline_and_compare(base: KnowledgeBase) -> None:
    events = await base.timeline()
    assert [e.claim_id for e in events] == ["CLM-001", "CLM-002"]
    assert [e.claim_id for e in await base.timeline("ENT-002")] == []
    comparison = await base.compare("CLM-001", "CLM-002")
    assert comparison is not None and comparison.relation is ClaimOrder.A_BEFORE_B
    assert await base.compare("CLM-001", "CLM-999") is None


@pytest.mark.parametrize(
    ("center", "depth", "expected"),
    [
        ("ENT-003", 0, {"ENT-003"}),
        ("ENT-003", 1, {"ENT-002", "ENT-003"}),
        ("ENT-003", 2, {"ENT-002", "ENT-003", "ENT-004"}),
        ("ENT-003", 3, {"ENT-001", "ENT-002", "ENT-003", "ENT-004"}),
    ],
)
async def test_the_neighbourhood_ignores_direction(
    base: KnowledgeBase, center: str, depth: int, expected: set[str]
) -> None:
    network = await base.network(center, depth)
    assert network is not None
    assert {n.entity_id for n in network.nodes} == expected
    # Stored direction is kept on the edges, whichever way they were walked.
    assert all(e.from_id != "ENT-003" for e in network.edges)


async def test_the_neighbourhood_of_an_unknown_entity_is_none_and_depth_is_capped(
    base: KnowledgeBase,
) -> None:
    assert await base.network("ENT-999", 2) is None
    capped = await base.network("ENT-003", 99)
    assert capped is not None and capped.depth == MAX_DEPTH


async def test_an_investigation_aggregates_everything_about_one_entity(base: KnowledgeBase) -> None:
    result = await base.investigate("Shipment 4821")
    assert result is not None
    assert result.entity.entity_id == "ENT-001"
    assert result.sources == ["a.txt:r1", "b.txt:r1"]
    assert len(result.claims) == 2
    assert len(result.conflicts) == 1
    assert {n.name for n in result.network.nodes} >= {"Shipment 4821", "Mumbai warehouse"}
    assert await base.investigate("nobody") is None


async def test_search_scores_identically(base: KnowledgeBase) -> None:
    hits = await base.search("Rahul warehouse")
    assert hits[0].claim.claim_id == "CLM-004"
    assert hits[0].score == 5
    assert hits[0].explanation == [
        "direct entity match",
        "keyword match: warehouse",
        "has source document",
    ]
    assert await base.search("completely unrelated") == []


# --- Neo4j only -----------------------------------------------------------------------------


async def test_a_run_round_trips_through_neo4j_exactly() -> None:
    store = await _neo4j()
    run_id = f"run_{uuid.uuid4().hex[:12]}"
    try:
        await store.save(run_id, SNAPSHOT)
        assert await store.load(run_id) == SNAPSHOT
        assert await store.load("run_000000000000") is None
    finally:
        await store.delete(run_id)
        await store.close()


async def test_two_runs_in_one_database_never_see_each_other() -> None:
    """Member 3 kept one global database; a later investigation saw an earlier one's claims."""
    store = await _neo4j()
    first, second = (f"run_{uuid.uuid4().hex[:12]}" for _ in range(2))
    other = SNAPSHOT.model_copy(
        update={"claims": [CLAIMS[0]], "conflicts": [], "relationships": []}
    )
    try:
        await store.save(first, SNAPSHOT)
        await store.save(second, other)
        assert len(await store.base(first).claims()) == 4
        assert len(await store.base(second).claims()) == 1
        assert await store.base(second).conflicts() == []
        network = await store.base(second).network("ENT-002", 3)
        assert network is not None and len(network.nodes) == 1
    finally:
        await store.delete(first)
        await store.delete(second)
        await store.close()


async def test_writing_a_run_again_replaces_it() -> None:
    store = await _neo4j()
    run_id = f"run_{uuid.uuid4().hex[:12]}"
    try:
        await store.save(run_id, SNAPSHOT)
        await store.save(run_id, SNAPSHOT)
        assert len(await store.base(run_id).entities()) == len(ENTITIES)
        await store.delete(run_id)
        assert not await store.exists(run_id)
    finally:
        await store.delete(run_id)
        await store.close()


async def test_a_conflict_is_an_edge_between_its_claims() -> None:
    """What the 3D view (Phase 32) will draw."""
    store = await _neo4j()
    run_id = f"run_{uuid.uuid4().hex[:12]}"
    try:
        await store.save(run_id, SNAPSHOT)
        rows = await store.read(
            "MATCH (a:Claim {run_id: $r})-[x:CONFLICTS_WITH]->(b:Claim {run_id: $r}) "
            "RETURN a.claim_id AS a, b.claim_id AS b, x.attribute AS attribute",
            r=run_id,
        )
        assert rows == [{"a": "CLM-001", "b": "CLM-002", "attribute": "arrival_date"}]
    finally:
        await store.delete(run_id)
        await store.close()


# --- choosing a store -------------------------------------------------------------------------


@pytest.fixture
def fresh_probe() -> Iterator[None]:
    graph_store.reset_graph_store_probe()
    yield
    graph_store.reset_graph_store_probe()


async def test_the_memory_setting_never_touches_neo4j(
    monkeypatch: pytest.MonkeyPatch, fresh_probe: None
) -> None:
    monkeypatch.setattr(get_settings(), "graph_store", GraphStoreName.MEMORY)
    base = await graph_store.open_knowledge_base("run_aaaaaaaaaaaa", SNAPSHOT)
    assert base.store == "memory"
    assert await graph_store.get_graph_store() is None


async def test_an_unreachable_neo4j_degrades_to_memory(
    monkeypatch: pytest.MonkeyPatch, fresh_probe: None
) -> None:
    monkeypatch.setattr(get_settings(), "graph_store", GraphStoreName.NEO4J)
    monkeypatch.setattr(get_settings(), "neo4j_uri", "bolt://127.0.0.1:1")
    try:
        base = await graph_store.open_knowledge_base("run_aaaaaaaaaaaa", SNAPSHOT)
        assert base.store == "memory"
        assert await base.claims() == CLAIMS
    finally:
        await graph_store.close_graph_store()


async def test_a_failed_write_degrades_to_memory_and_never_raises(
    monkeypatch: pytest.MonkeyPatch, fresh_probe: None
) -> None:
    async def broken(self: Neo4jGraphStore, run_id: str, snapshot: KnowledgeSnapshot) -> None:
        raise RuntimeError("disk full")

    store = await _neo4j()
    await store.close()
    monkeypatch.setattr(get_settings(), "graph_store", GraphStoreName.NEO4J)
    monkeypatch.setattr(Neo4jGraphStore, "save", broken)
    try:
        base = await graph_store.open_knowledge_base("run_aaaaaaaaaaaa", SNAPSHOT)
        assert base.store == "memory"
    finally:
        await graph_store.close_graph_store()


async def test_a_reachable_neo4j_holds_the_run(
    monkeypatch: pytest.MonkeyPatch, fresh_probe: None
) -> None:
    store = await _neo4j()
    await store.close()
    monkeypatch.setattr(get_settings(), "graph_store", GraphStoreName.NEO4J)
    run_id = f"run_{uuid.uuid4().hex[:12]}"
    try:
        base = await graph_store.open_knowledge_base(run_id, SNAPSHOT)
        assert base.store == "neo4j"
        assert await base.claims() == CLAIMS
        live = await graph_store.get_graph_store()
        assert live is not None
        await live.delete(run_id)
    finally:
        await graph_store.close_graph_store()


async def test_a_finding_cites_the_claims_and_documents_it_rests_on() -> None:
    """Phase 30: what the 3D view lights up when a finding is clicked. Unresolved citations get
    no edge, because they point at nothing a tool produced."""
    from app.schemas.common import SourceLocator
    from app.schemas.evidence import EvidenceRef, ResolutionStatus
    from app.schemas.finding import Finding

    def ref(doc: str, row: int, resolved: bool = True) -> EvidenceRef:
        return EvidenceRef(
            locator=SourceLocator(document_id=doc, document_name=doc, row=row),
            resolution=ResolutionStatus.RESOLVED if resolved else ResolutionStatus.UNRESOLVED,
        )

    finding = Finding(
        finding_id="F-001",
        claim="The reports give 14 and 16 September.",
        evidence=[ref("a.txt", 1), ref("b.txt", 1), ref("z.txt", 9, resolved=False)],
    )
    store = await _neo4j()
    run_id = f"run_{uuid.uuid4().hex[:12]}"
    try:
        await store.save(run_id, SNAPSHOT)
        await store.save_findings(run_id, [finding])
        await store.save_findings(run_id, [finding])  # replaces, never duplicates
        rows = await store.read(
            "MATCH (f:Finding {run_id: $r})-[c:CITES]->(n) "
            "RETURN labels(n)[0] AS label, c.source AS source ORDER BY label, source",
            r=run_id,
        )
        assert rows == [
            {"label": "Claim", "source": "a.txt:r1"},
            {"label": "Claim", "source": "b.txt:r1"},
            {"label": "Document", "source": "a.txt:r1"},
            {"label": "Document", "source": "b.txt:r1"},
        ]
    finally:
        await store.delete(run_id)
        await store.close()
