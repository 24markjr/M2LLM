"""Phase 31: the knowledge routes.

Member 3's endpoints, per mission, plus the graph, node and trail routes the 3D view uses. Missions
are registered with a finished result, so these test the HTTP layer and the views, not the pipeline.
"""

from __future__ import annotations

import json
import uuid
from collections.abc import AsyncIterator

import pytest
from httpx import ASGITransport, AsyncClient

from app.api.app import create_app
from app.api.registry import MissionRecord, get_registry, reset_registry
from app.api.v1 import knowledge as knowledge_routes
from app.core.config import GraphStoreName, get_settings
from app.integrations import graph_store
from app.integrations.neo4j_store import Neo4jGraphStore
from app.intelligence.knowledge.conflicts import detect_conflicts
from app.llm.echo import EchoProvider
from app.orchestration.mission import MissionResult, MissionStatus, Stage
from app.schemas.common import SourceLocator, new_run_id
from app.schemas.evidence import EvidenceRef, ResolutionStatus
from app.schemas.finding import Finding
from app.schemas.knowledge import (
    EntityType,
    ExtractionStats,
    KnowledgeClaim,
    KnowledgeEntity,
    KnowledgeRelationship,
    KnowledgeSnapshot,
)
from app.schemas.objective import Objective
from app.schemas.verification import VerificationResult, VerificationStatus

ENTITIES = [
    KnowledgeEntity(
        entity_id="ENT-001",
        name="Shipment 4821",
        entity_type=EntityType.SHIPMENT,
        sources=["a.txt:r1", "b.txt:r1"],
    ),
    KnowledgeEntity(
        entity_id="ENT-002",
        name="Rahul Sharma",
        entity_type=EntityType.PERSON,
        sources=["a.txt:r1"],
    ),
]
RELATIONSHIPS = [
    KnowledgeRelationship(
        relationship_id="REL-001",
        subject_id="ENT-002",
        predicate="received",
        object_id="ENT-001",
        source="a.txt:r1",
    )
]


def _claim(n: int, attribute: str, value: str, source: str) -> KnowledgeClaim:
    return KnowledgeClaim(
        claim_id=f"CLM-{n:03d}",
        entity_id="ENT-001",
        attribute=attribute,
        value=value,
        source=source,
        document_id=source.split(":")[0],
        line=1,
    )


CLAIMS = [
    _claim(1, "arrival_date", "14 September", "a.txt:r1"),
    _claim(2, "arrival_date", "16 September", "b.txt:r1"),
]
SNAPSHOT = KnowledgeSnapshot(
    entities=ENTITIES,
    relationships=RELATIONSHIPS,
    claims=CLAIMS,
    conflicts=detect_conflicts(CLAIMS, ENTITIES),
    stats=ExtractionStats(documents=2, chunks=2, llm_calls=2, claims=2),
)


def _ref(source: str, *, resolved: bool = True) -> EvidenceRef:
    document, _, row = source.rpartition(":r")
    return EvidenceRef(
        locator=SourceLocator(document_id=document, document_name=document, row=int(row)),
        resolution=ResolutionStatus.RESOLVED if resolved else ResolutionStatus.UNRESOLVED,
    )


FINDING = Finding(
    finding_id="F-001",
    claim="The reports give 14 and 16 September for Shipment 4821's arrival.",
    evidence=[_ref("a.txt:r1"), _ref("b.txt:r1"), _ref("c.txt:r5")],
    verification=VerificationResult(status=VerificationStatus.SUPPORTED, confidence=0.9),
)


@pytest.fixture(autouse=True)
def _clean_registry() -> None:
    reset_registry()


async def _client() -> AsyncClient:
    return AsyncClient(transport=ASGITransport(app=create_app()), base_url="http://test")


def _mission(
    *,
    knowledge: KnowledgeSnapshot | None = SNAPSHOT,
    store: str = "memory",
    status: MissionStatus = MissionStatus.COMPLETED,
    run_id: str | None = None,
) -> MissionRecord:
    record = MissionRecord(run_id or new_run_id(), Objective(text="Compare the reports."), [])
    record.status = status
    record.stage = Stage.DONE if status is MissionStatus.COMPLETED else Stage.EXECUTING
    record.result = MissionResult(
        run_id=record.run_id,
        objective=record.objective,
        status=status,
        knowledge=knowledge,
        knowledge_store=store if knowledge else "",
        knowledge_pass_task_id="task_004" if knowledge else None,
        findings=[FINDING],
    )
    get_registry()._missions[record.run_id] = record
    return record


def _url(record: MissionRecord, path: str = "") -> str:
    return f"/api/v1/missions/{record.run_id}/knowledge{path}"


# --- errors -----------------------------------------------------------------------------


async def test_an_unknown_mission_is_a_404_with_a_code() -> None:
    async with await _client() as client:
        response = await client.get("/api/v1/missions/run_aaaaaaaaaaaa/knowledge")
    assert response.status_code == 404
    assert response.json()["error_code"] == "MISSION_NOT_FOUND"


async def test_a_finished_mission_without_knowledge_is_a_404_saying_so() -> None:
    record = _mission(knowledge=None)
    async with await _client() as client:
        response = await client.get(_url(record))
    assert response.status_code == 404
    assert response.json()["error_code"] == "KNOWLEDGE_NOT_BUILT"


async def test_a_running_mission_without_knowledge_yet_is_a_409_to_retry() -> None:
    record = _mission(knowledge=None, status=MissionStatus.RUNNING)
    async with await _client() as client:
        response = await client.get(_url(record, "/claims"))
    assert response.status_code == 409
    assert response.json()["error_code"] == "MISSION_NOT_FINISHED"


@pytest.mark.parametrize(
    ("path", "code"),
    [
        ("/claims/CLM-999", "CLAIM_NOT_FOUND"),
        ("/entities/ENT-999/network", "ENTITY_NOT_FOUND"),
        ("/investigation?name=nobody", "ENTITY_NOT_FOUND"),
        ("/nodes/ENT-999", "NODE_NOT_FOUND"),
        ("/timeline/compare?claim_a=CLM-001&claim_b=CLM-999", "CLAIM_NOT_FOUND"),
    ],
)
async def test_unknown_ids_are_typed_404s_not_error_strings(path: str, code: str) -> None:
    """Member 3's API answered these with {"error": ...} and a 200."""
    record = _mission()
    async with await _client() as client:
        response = await client.get(_url(record, path))
    assert response.status_code == 404
    assert response.json()["error_code"] == code


# --- Member 3's endpoints, per mission ------------------------------------------------------


async def test_the_summary_and_the_mission_detail_report_the_knowledge_base() -> None:
    record = _mission()
    async with await _client() as client:
        summary = (await client.get(_url(record))).json()
        detail = (await client.get(f"/api/v1/missions/{record.run_id}")).json()
    assert summary["store"] == "memory"
    assert (summary["entities"], summary["claims"], summary["conflicts"]) == (2, 2, 1)
    assert summary["knowledge_pass_task_id"] == "task_004"
    assert detail["knowledge_store"] == "memory"
    assert detail["knowledge_conflicts"] == 1


async def test_every_member_3_query_answers_per_mission() -> None:
    record = _mission()
    async with await _client() as client:
        entities = (await client.get(_url(record, "/entities"))).json()
        found = (await client.get(_url(record, "/entities?name=rahul"))).json()
        relationships = (await client.get(_url(record, "/relationships?entity_id=ENT-001"))).json()
        claims = (await client.get(_url(record, "/claims?entity_id=ENT-001"))).json()
        one = (await client.get(_url(record, "/claims/CLM-002"))).json()
        conflicts = (await client.get(_url(record, "/conflicts"))).json()
        timeline = (await client.get(_url(record, "/timeline"))).json()
        compare = (
            await client.get(_url(record, "/timeline/compare?claim_a=CLM-001&claim_b=CLM-002"))
        ).json()
        network = (await client.get(_url(record, "/entities/ENT-002/network?depth=1"))).json()
        investigation = (await client.get(_url(record, "/investigation?name=Shipment 4821"))).json()
        search = (await client.get(_url(record, "/search?q=shipment arrival"))).json()

    assert [e["entity_id"] for e in entities] == ["ENT-001", "ENT-002"]
    assert [e["name"] for e in found] == ["Rahul Sharma"]
    assert [r["relationship_id"] for r in relationships] == ["REL-001"]
    assert [c["claim_id"] for c in claims] == ["CLM-001", "CLM-002"]
    assert one["value"] == "16 September"
    assert conflicts[0]["attribute"] == "arrival_date"
    assert [e["relation_to_previous"] for e in timeline] == [None, "AFTER"]
    assert compare["relation"] == "A_BEFORE_B"
    assert {n["entity_id"] for n in network["nodes"]} == {"ENT-001", "ENT-002"}
    assert len(investigation["conflicts"]) == 1
    assert search[0]["explanation"][0] == "direct entity match"


async def test_claims_filter_by_grounding() -> None:
    invented = _claim(3, "arrival_date", "20 September", "b.txt:r1").model_copy(
        update={"grounded": False}
    )
    record = _mission(knowledge=SNAPSHOT.model_copy(update={"claims": [*CLAIMS, invented]}))
    async with await _client() as client:
        grounded = (await client.get(_url(record, "/claims?grounded=true"))).json()
        ungrounded = (await client.get(_url(record, "/claims?grounded=false"))).json()
    assert len(grounded) == 2
    assert [c["claim_id"] for c in ungrounded] == ["CLM-003"]


# --- the views for the 3D explorer ------------------------------------------------------------


async def test_the_graph_has_entities_with_claim_sub_nodes_documents_and_the_finding() -> None:
    record = _mission()
    async with await _client() as client:
        graph = (await client.get(_url(record, "/graph"))).json()

    kinds = {n["id"]: n["kind"] for n in graph["nodes"]}
    assert kinds == {
        "ENT-001": "ENTITY",
        "ENT-002": "ENTITY",
        "CLM-001": "CLAIM",
        "CLM-002": "CLAIM",
        "DOC:a.txt": "DOCUMENT",
        "DOC:b.txt": "DOCUMENT",
        "F-001": "FINDING",
    }
    claim = next(n for n in graph["nodes"] if n["id"] == "CLM-001")
    assert claim["parent"] == "ENT-001", "a claim is a sub-node of its entity"
    assert claim["conflict_count"] == 1
    shipment = next(n for n in graph["nodes"] if n["id"] == "ENT-001")
    assert (shipment["claim_count"], shipment["conflict_count"]) == (2, 1)
    links = {(link["source"], link["target"], link["kind"]) for link in graph["links"]}
    assert ("CLM-001", "CLM-002", "CONFLICTS_WITH") in links
    assert ("F-001", "CLM-001", "CITES") in links
    assert ("ENT-002", "ENT-001", "RELATES") in links


async def test_a_focused_graph_is_the_neighbourhood() -> None:
    record = _mission()
    async with await _client() as client:
        graph = (await client.get(_url(record, "/graph?focus=ENT-002&depth=0"))).json()
    entities = [n["id"] for n in graph["nodes"] if n["kind"] == "ENTITY"]
    assert entities == ["ENT-002"]
    assert graph["focus"] == "ENT-002"


@pytest.mark.parametrize(
    ("node_id", "kind"),
    [("ENT-001", "ENTITY"), ("CLM-001", "CLAIM"), ("DOC:a.txt", "DOCUMENT"), ("F-001", "FINDING")],
)
async def test_every_node_kind_has_a_detail_for_the_pop_up(node_id: str, kind: str) -> None:
    record = _mission()
    async with await _client() as client:
        detail = (await client.get(_url(record, f"/nodes/{node_id}"))).json()
    assert detail["node"]["kind"] == kind
    if kind == "ENTITY":
        assert len(detail["claims"]) == 2 and len(detail["conflicts"]) == 1
        assert detail["documents"] == ["a.txt", "b.txt"]
    if kind == "CLAIM":
        assert detail["entity"]["name"] == "Shipment 4821"
        assert len(detail["conflicts"]) == 1
    if kind == "FINDING":
        assert detail["finding_status"] == "SUPPORTED"


async def test_a_finding_trail_lights_up_what_it_rests_on_and_reports_what_matched_nothing() -> (
    None
):
    record = _mission()
    async with await _client() as client:
        trail = (await client.get(f"/api/v1/missions/{record.run_id}/findings/F-001/trail")).json()
        missing = await client.get(f"/api/v1/missions/{record.run_id}/findings/F-999/trail")
    assert trail["node_ids"] == [
        "F-001",
        "CLM-001",
        "CLM-002",
        "ENT-001",
        "DOC:a.txt",
        "DOC:b.txt",
        "DOC:c.txt",
    ]
    assert trail["unmatched_sources"] == ["c.txt:r5"]
    assert trail["status"] == "SUPPORTED"
    assert missing.status_code == 404
    assert missing.json()["error_code"] == "FINDING_NOT_FOUND"


# --- analyze, without a mission ---------------------------------------------------------------


async def test_analyze_builds_a_knowledge_base_from_documents_and_stores_nothing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    replies = [
        json.dumps(
            {
                "entities": [{"name": "Project Aurora", "type": "OTHER"}],
                "relationships": [],
                "claims": [
                    {
                        "entity": "Project Aurora",
                        "attribute": "approved_budget",
                        "value": "INR 380,000",
                        "line": 17,
                    }
                ],
            }
        )
    ]
    provider = EchoProvider(responses={"knowledge": replies})
    monkeypatch.setattr(knowledge_routes, "get_provider", lambda: provider)
    async with await _client() as client:
        response = await client.post(
            "/api/v1/knowledge/analyze",
            json={"documents": ["aurora_project_report.txt", "no_such_file.txt"]},
        )
    body = response.json()
    assert response.status_code == 200
    assert body["snapshot"]["claims"][0]["value"] == "INR 380,000"
    assert body["graph"]["store"] == "memory"
    assert body["excluded"] == ["no_such_file.txt"]


async def test_analyze_refuses_when_nothing_is_readable() -> None:
    async with await _client() as client:
        response = await client.post("/api/v1/knowledge/analyze", json={"documents": ["nope.txt"]})
    assert response.status_code == 422
    assert response.json()["error_code"] == "NO_READABLE_DOCUMENTS"


# --- Neo4j: answered from the graph, including after a restart ---------------------------------


@pytest.fixture
async def neo4j_run(monkeypatch: pytest.MonkeyPatch) -> AsyncIterator[str]:
    settings = get_settings()
    probe = Neo4jGraphStore.connect(
        settings.neo4j_uri, settings.neo4j_user, settings.neo4j_password, settings.neo4j_database
    )
    reachable = await probe.available()
    await probe.close()
    if not reachable:
        pytest.skip("Neo4j not reachable: start it with `docker compose up -d neo4j`")
    monkeypatch.setattr(settings, "graph_store", GraphStoreName.NEO4J)
    graph_store.reset_graph_store_probe()
    run_id = f"run_{uuid.uuid4().hex[:12]}"
    store = await graph_store.get_graph_store()
    assert store is not None
    await store.save(run_id, SNAPSHOT)
    try:
        yield run_id
    finally:
        await store.delete(run_id)
        await graph_store.close_graph_store()


async def test_a_mission_whose_knowledge_is_in_neo4j_is_answered_from_neo4j(neo4j_run: str) -> None:
    record = _mission(store="neo4j", run_id=neo4j_run)
    async with await _client() as client:
        summary = (await client.get(_url(record))).json()
        conflicts = (await client.get(_url(record, "/conflicts"))).json()
    assert summary["store"] == "neo4j"
    assert conflicts[0]["attribute"] == "arrival_date"


async def test_after_a_restart_the_knowledge_is_still_served_from_neo4j(neo4j_run: str) -> None:
    """The registry is in memory and empty after a restart; the graph is not."""
    async with await _client() as client:
        summary = await client.get(f"/api/v1/missions/{neo4j_run}/knowledge")
        graph = (await client.get(f"/api/v1/missions/{neo4j_run}/knowledge/graph")).json()
    assert summary.status_code == 200
    assert summary.json()["claims"] == 2
    assert {n["kind"] for n in graph["nodes"]} == {"ENTITY", "CLAIM", "DOCUMENT"}, (
        "findings live in the registry, so after a restart the graph has none"
    )
