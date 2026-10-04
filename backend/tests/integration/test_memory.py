"""Phase 33: memory against the real stores.

Semantic memory runs one suite on both stores (Postgres and Neo4j), as the knowledge base does: the
two must answer alike, or what a person finds in memory would depend on configuration. Episodic
memory is Postgres only. The last tests are the phase's "done when", through the API.

Every name carries a random suffix, and everything written is removed, because semantic memory is
shared across runs: a test that left "Rahul Sharma" behind would show up in a developer's memory.
"""

from __future__ import annotations

import asyncio
import uuid
from collections.abc import AsyncIterator, Iterator

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import delete

from app.api.app import create_app
from app.core.config import GraphStoreName, get_settings
from app.database.repositories import RunRepository
from app.database.session import database_available, dispose_engine, session_scope
from app.integrations import graph_store
from app.integrations.graph_store import close_graph_store
from app.integrations.neo4j_store import Neo4jGraphStore
from app.memory.distill import make_fact
from app.memory.episodic import EpisodicMemory
from app.memory.semantic import PostgresSemanticMemory, SemanticMemory
from app.memory.service import record_run
from app.models.tables import AgentRun
from app.orchestration.mission import MissionResult, MissionStatus
from app.schemas.common import SourceLocator, new_run_id
from app.schemas.evidence import EvidenceRef, ResolutionStatus
from app.schemas.execution import ExecutionState, RunStatus
from app.schemas.finding import Finding
from app.schemas.knowledge import (
    EntityType,
    KnowledgeClaim,
    KnowledgeEntity,
    KnowledgeRelationship,
    KnowledgeSnapshot,
)
from app.schemas.memory import (
    ArchivedInvestigation,
    Episode,
    FactKind,
    FactSupport,
    KnownEntity,
    WorkingMemorySnapshot,
)
from app.schemas.objective import Objective
from app.schemas.verification import VerificationResult, VerificationStatus

pytestmark = pytest.mark.integration


def _db_available() -> bool:
    async def probe() -> bool:
        try:
            return await database_available()
        finally:
            await dispose_engine()

    try:
        return asyncio.run(probe())
    except Exception:  # noqa: BLE001 - availability probe
        return False


DB_AVAILABLE = _db_available()
requires_db = pytest.mark.skipif(
    not DB_AVAILABLE, reason="no database reachable (docker compose up -d postgres)"
)


@pytest.fixture
def sfx() -> str:
    return uuid.uuid4().hex[:6]


async def _runs(*objectives: str) -> list[str]:
    """Run rows for memory to reference (episodes and support have a foreign key to the run)."""
    ids = []
    async with session_scope() as session:
        for objective in objectives:
            state = ExecutionState(
                run_id=new_run_id(), objective=Objective(text=objective), status=RunStatus.COMPLETED
            )
            await RunRepository(session).create(state)
            ids.append(state.run_id)
    return ids


async def _drop_runs(run_ids: list[str]) -> None:
    async with session_scope() as session:
        await session.execute(delete(AgentRun).where(AgentRun.id.in_(run_ids)))


async def _neo4j() -> Neo4jGraphStore:
    settings = get_settings()
    store = Neo4jGraphStore.connect(
        settings.neo4j_uri, settings.neo4j_user, settings.neo4j_password, settings.neo4j_database
    )
    if not await store.available():
        await store.close()
        pytest.skip("Neo4j not reachable: start it with `docker compose up -d neo4j`")
    return store


# --- semantic memory: one suite, both stores ----------------------------------------------


class _Memory:
    def __init__(self, memory: SemanticMemory, runs: list[str]) -> None:
        self.memory = memory
        self.runs = runs


@pytest.fixture(params=["postgres", "neo4j"])
async def semantic(request: pytest.FixtureRequest) -> AsyncIterator[_Memory]:
    if request.param == "postgres":
        if not DB_AVAILABLE:
            pytest.skip("no database reachable")
        runs = await _runs("first", "second")
        memory: SemanticMemory = PostgresSemanticMemory()
        try:
            yield _Memory(memory, runs)
        finally:
            for run_id in runs:
                await memory.forget(run_id)
            await _drop_runs(runs)
        return
    store = await _neo4j()
    runs = [new_run_id(), new_run_id()]
    memory = store.semantic_memory()
    try:
        yield _Memory(memory, runs)
    finally:
        for run_id in runs:
            await memory.forget(run_id)
        await store.close()


def _entity(name: str, run_id: str, entity_type: EntityType = EntityType.PERSON) -> KnownEntity:
    from app.intelligence.knowledge.store import normalize_name

    return KnownEntity(
        key=normalize_name(name), name=name, entity_types=[entity_type], runs=[run_id]
    )


def _supported(kind: FactKind, subject: str, predicate: str, obj: str, run_id: str, source: str):
    fact = make_fact(kind, subject, predicate, obj)
    fact.support.append(FactSupport(run_id=run_id, source=source))
    return fact


async def test_two_runs_asserting_a_fact_give_it_a_support_of_two(
    semantic: _Memory, sfx: str
) -> None:
    first, second = semantic.runs
    rahul, abc = f"Rahul Sharma {sfx}", f"ABC Logistics {sfx}"
    for run_id, source in ((first, "staff.txt:r3"), (second, "roster.txt:r7")):
        await semantic.memory.record(
            [_entity(rahul, run_id), _entity(abc, run_id, EntityType.ORG)],
            [_supported(FactKind.RELATION, rahul, "works_for", abc, run_id, source)],
        )
    found = await semantic.memory.entity(rahul.upper())
    assert found is not None
    assert found.entity.runs == sorted([first, second])
    (fact,) = found.facts
    assert fact.support_count == 2
    assert fact.runs == sorted([first, second])
    # The organisation sees the relation too, as its object.
    org = await semantic.memory.entity(abc)
    assert org is not None and [f.fact_id for f in org.facts] == [fact.fact_id]


async def test_recording_the_same_run_twice_changes_nothing(semantic: _Memory, sfx: str) -> None:
    run_id = semantic.runs[0]
    name = f"Shipment {sfx}"
    facts = [
        _supported(FactKind.ATTRIBUTE, name, "arrival_date", "14 September", run_id, "a.txt:r1")
    ]
    for _ in range(2):
        await semantic.memory.record([_entity(name, run_id, EntityType.SHIPMENT)], facts)
    found = await semantic.memory.entity(name)
    assert found is not None
    assert found.entity.runs == [run_id]
    assert [f.support_count for f in found.facts] == [1]


async def test_facts_by_subject_and_predicate_best_supported_first(
    semantic: _Memory, sfx: str
) -> None:
    first, second = semantic.runs
    name = f"Shipment {sfx}"
    early = _supported(FactKind.ATTRIBUTE, name, "Arrival Date", "14 September", first, "a.txt:r1")
    late = _supported(FactKind.ATTRIBUTE, name, "arrival_date", "16 September", first, "b.txt:r1")
    late_again = _supported(
        FactKind.ATTRIBUTE, name, "arrival_date", "16 September", second, "c.txt:r2"
    )
    await semantic.memory.record([_entity(name, first)], [early, late])
    await semantic.memory.record([_entity(name, second)], [late_again])

    facts = await semantic.memory.facts(subject=f"the shipment  {sfx}", predicate="Arrival-Date")
    assert [(f.object, f.support_count) for f in facts] == [
        ("16 September", 2),
        ("14 September", 1),
    ]
    assert len(await semantic.memory.facts(subject=name, limit=1)) == 1
    assert await semantic.memory.facts(subject=name, predicate="weight") == []


async def test_forgetting_a_run_removes_only_what_it_alone_supported(
    semantic: _Memory, sfx: str
) -> None:
    first, second = semantic.runs
    name = f"Shipment {sfx}"
    shared = [_supported(FactKind.ATTRIBUTE, name, "status", "delayed", first, "a.txt:r1")]
    own = [_supported(FactKind.ATTRIBUTE, name, "carrier", "ABC", first, "a.txt:r2")]
    await semantic.memory.record([_entity(name, first)], shared + own)
    await semantic.memory.record(
        [_entity(name, second)],
        [_supported(FactKind.ATTRIBUTE, name, "status", "delayed", second, "b.txt:r1")],
    )

    await semantic.memory.forget(first)
    found = await semantic.memory.entity(name)
    assert found is not None
    assert found.entity.runs == [second]
    assert [(f.predicate, f.support_count) for f in found.facts] == [("status", 1)]

    await semantic.memory.forget(second)
    assert await semantic.memory.entity(name) is None


async def test_an_unknown_entity_is_none(semantic: _Memory, sfx: str) -> None:
    assert await semantic.memory.entity(f"nobody {sfx}") is None
    assert await semantic.memory.entity("   ") is None


# --- episodic memory (Postgres) ---------------------------------------------------------------


@pytest.fixture
async def episodic_runs() -> AsyncIterator[list[str]]:
    runs = await _runs("Who received shipment 4821?", "Compare the Aurora reports")
    yield runs
    await _drop_runs(runs)


def _episode(
    run_id: str, fid: str, objective: str, claim: str, status: str = "SUPPORTED"
) -> Episode:
    return Episode(
        episode_id=f"{run_id}:{fid}",
        run_id=run_id,
        objective=objective,
        claim=claim,
        sources=["a.txt:r1"],
        verification_status=status,
    )


def _archive(run_id: str, objective: str) -> ArchivedInvestigation:
    return ArchivedInvestigation(
        run_id=run_id,
        objective=objective,
        snapshot=WorkingMemorySnapshot(investigation_id=run_id, objective=objective),
    )


@requires_db
async def test_episodes_are_searched_in_objective_and_claim_newest_first(
    episodic_runs: list[str], sfx: str
) -> None:
    first, second = episodic_runs
    async with session_scope() as session:
        memory = EpisodicMemory(session)
        await memory.record(
            _archive(first, f"Who received shipment {sfx}?"),
            [
                _episode(
                    first, "F-001", f"Who received shipment {sfx}?", "Rahul Sharma signed for it."
                )
            ],
        )
        await memory.record(
            _archive(second, "Compare the reports"),
            [
                _episode(
                    second,
                    "F-001",
                    "Compare the reports",
                    f"Shipment {sfx} arrived late.",
                    "CONTRADICTED",
                ),
                _episode(second, "F-002", "Compare the reports", "The budget is unchanged."),
            ],
        )

    async with session_scope() as session:
        memory = EpisodicMemory(session)
        hits = await memory.search(f"SHIPMENT {sfx}")
        # One matched on its objective, one on its claim; the rejected one is kept with its status.
        assert {(h.run_id, h.verification_status) for h in hits} == {
            (first, "SUPPORTED"),
            (second, "CONTRADICTED"),
        }
        assert [h.created_at for h in hits] == sorted((h.created_at for h in hits), reverse=True)
        assert len(await memory.search("", limit=1)) == 1


@requires_db
async def test_a_percent_sign_is_searched_for_not_a_wildcard(
    episodic_runs: list[str], sfx: str
) -> None:
    run_id = episodic_runs[0]
    async with session_scope() as session:
        await EpisodicMemory(session).record(
            _archive(run_id, "x"),
            [
                _episode(run_id, "F-001", "x", f"Costs rose 12% {sfx}"),
                _episode(run_id, "F-002", "x", f"Costs rose 12 {sfx}"),
            ],
        )
    async with session_scope() as session:
        hits = await EpisodicMemory(session).search(f"12% {sfx}")
    assert [h.claim for h in hits] == [f"Costs rose 12% {sfx}"]


@requires_db
async def test_recording_a_run_again_replaces_its_episodes(episodic_runs: list[str]) -> None:
    run_id = episodic_runs[0]
    async with session_scope() as session:
        memory = EpisodicMemory(session)
        await memory.record(
            _archive(run_id, "old"),
            [_episode(run_id, "F-001", "old", "a"), _episode(run_id, "F-002", "old", "b")],
        )
        await memory.record(_archive(run_id, "new"), [_episode(run_id, "F-001", "new", "c")])
    async with session_scope() as session:
        memory = EpisodicMemory(session)
        assert [e.claim for e in await memory.episodes_of(run_id)] == ["c"]
        archived = await memory.investigation(run_id)
        assert archived is not None and archived.objective == "new"
        assert await memory.investigation("run_000000000000") is None


# --- done when: two missions, one known entity, through the API ----------------------------


def _mission(run_id: str, sfx: str, source: str, value: str) -> MissionResult:
    rahul, abc = f"Rahul Sharma {sfx}", f"ABC Logistics {sfx}"
    document, _, row = source.rpartition(":r")
    return MissionResult(
        run_id=run_id,
        objective=Objective(text=f"Who received shipment {sfx}?"),
        status=MissionStatus.COMPLETED,
        knowledge=KnowledgeSnapshot(
            entities=[
                KnowledgeEntity(entity_id="ENT-001", name=rahul, entity_type=EntityType.PERSON),
                KnowledgeEntity(entity_id="ENT-002", name=abc, entity_type=EntityType.ORG),
            ],
            relationships=[
                KnowledgeRelationship(
                    relationship_id="REL-001",
                    subject_id="ENT-001",
                    predicate="works_for",
                    object_id="ENT-002",
                    source=source,
                )
            ],
            claims=[
                KnowledgeClaim(
                    claim_id="CLM-001",
                    entity_id="ENT-001",
                    attribute="shift",
                    value=value,
                    source=source,
                    document_id=document,
                    line=1,
                )
            ],
        ),
        findings=[
            Finding(
                finding_id="F-001",
                claim=f"{rahul} of {abc} received the shipment.",
                evidence=[
                    EvidenceRef(
                        locator=SourceLocator(
                            document_id=document, document_name=document, row=int(row)
                        ),
                        resolution=ResolutionStatus.RESOLVED,
                    )
                ],
                verification=VerificationResult(
                    status=VerificationStatus.SUPPORTED, confidence=0.9
                ),
            )
        ],
    )


@pytest.fixture(params=["postgres", "neo4j"])
def fact_store(request: pytest.FixtureRequest, monkeypatch: pytest.MonkeyPatch) -> Iterator[str]:
    store = GraphStoreName.MEMORY if request.param == "postgres" else GraphStoreName.NEO4J
    monkeypatch.setattr(get_settings(), "graph_store", store)
    graph_store.reset_graph_store_probe()
    yield request.param
    graph_store.reset_graph_store_probe()


@requires_db
async def test_two_missions_leave_one_known_entity_with_supported_facts(
    fact_store: str, sfx: str
) -> None:
    if fact_store == "neo4j":
        await _neo4j()  # skips when Neo4j is down
    first, second = await _runs("first", "second")
    try:
        await record_run(_mission(first, sfx, "staff.txt:r3", "night"))
        await record_run(_mission(second, sfx, "roster.txt:r7", "night"))

        async with AsyncClient(transport=ASGITransport(app=create_app()), base_url="http://t") as c:
            status = (await c.get("/api/v1/memory")).json()
            assert status == {"episodic": True, "semantic_store": fact_store}

            entity = (await c.get(f"/api/v1/memory/entities/rahul sharma {sfx}")).json()
            assert entity["entity"]["runs"] == sorted([first, second])
            facts = {(f["predicate"], f["object"]): f for f in entity["facts"]}
            assert facts[("shift", "night")]["support_count"] == 2
            assert facts[("works_for", f"ABC Logistics {sfx}")]["support_count"] == 2
            assert all("confidence" not in f for f in entity["facts"])

            episodes = (await c.get("/api/v1/memory/episodes", params={"q": sfx})).json()
            assert sorted(e["run_id"] for e in episodes) == sorted([first, second])

            archived = (await c.get(f"/api/v1/memory/investigations/{first}")).json()
            assert archived["investigation"]["objective"] == f"Who received shipment {sfx}?"
            assert [e["episode_id"] for e in archived["episodes"]] == [f"{first}:F-001"]

            by_subject = (
                await c.get("/api/v1/memory/facts", params={"subject": f"Rahul Sharma {sfx}"})
            ).json()
            assert len(by_subject) == 2

            missing = await c.get(f"/api/v1/memory/entities/nobody {sfx}")
            assert missing.status_code == 404
            assert missing.json()["error_code"] == "MEMORY_NOT_FOUND"
    finally:
        if fact_store == "neo4j":
            store = await graph_store.get_graph_store()
            assert store is not None
            for run_id in (first, second):
                await store.semantic_memory().forget(run_id)
            await close_graph_store()
        else:
            for run_id in (first, second):
                await PostgresSemanticMemory().forget(run_id)
        await _drop_runs([first, second])
