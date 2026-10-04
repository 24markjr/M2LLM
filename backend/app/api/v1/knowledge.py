"""Knowledge routes (Phase 31): Member 3's API, per mission, plus what the 3D view needs.

| Member 3 | JARVIS |
|---|---|
| `POST /ingest` | `POST /api/v1/knowledge/analyze`: documents in, knowledge out, no mission |
| `GET /entities`, `/find_entity?name=` | `GET .../knowledge/entities?name=` |
| `GET /relationships`, `/relationships/{id}` | `GET .../knowledge/relationships?entity_id=` |
| `GET /claims` | `GET .../knowledge/claims?entity_id=&grounded=` |
| `GET /evidence/{claim_id}` | `GET .../knowledge/claims/{claim_id}` |
| `GET /contradictions` | `GET .../knowledge/conflicts?entity_id=` |
| `GET /timeline`, `/entity/{id}/timeline` | `GET .../knowledge/timeline?entity_id=` |
| `GET /timeline/compare` | `GET .../knowledge/timeline/compare?claim_a=&claim_b=` |
| `GET /entity/{id}/network?depth=` | `GET .../knowledge/entities/{entity_id}/network?depth=` |
| `GET /investigation/{name}` | `GET .../knowledge/investigation?name=` |
| `GET /search?q=&depth=` | `GET .../knowledge/search?q=&depth=` |
| (new) | `GET .../knowledge`: summary; `.../knowledge/graph`; `.../knowledge/nodes/{node_id}` |
| (new) | `GET .../findings/{finding_id}/trail`: the subgraph a finding rests on |

`...` is `/api/v1/missions/{run_id}`. Differences from the original, each deliberate:

- **Per mission.** Member 3's API answered from one global database.
- **Errors are typed.** The original answered an unknown id with `{"error": ...}` and a 200.
- **CORS stays on the allow-list.** The original allowed every origin.
- **Knowledge outlives the API process when it is in Neo4j.** A mission that is no longer in the
  in-memory registry (the API restarted) is still answered from Neo4j. Its findings are not, so
  its trail is unavailable and the graph has no finding nodes.
"""

from __future__ import annotations

from fastapi import APIRouter, Query, status
from pydantic import Field

from app.api.errors import ApiError, MissionNotFinishedError, MissionNotFoundError
from app.api.registry import get_registry
from app.core.agent_config import get_knowledge_policy
from app.integrations.graph_store import get_graph_store
from app.intelligence.knowledge.base import (
    MAX_DEPTH,
    InMemoryKnowledgeBase,
    KnowledgeBase,
)
from app.intelligence.knowledge.extraction import KnowledgeExtractor
from app.intelligence.knowledge.view import build_view, finding_trail, node_detail
from app.llm import get_provider
from app.schemas.common import JarvisModel
from app.schemas.finding import Finding
from app.schemas.knowledge import (
    ClaimComparison,
    ClaimConflict,
    EntityInvestigation,
    EntityNetwork,
    ExtractionStats,
    FindingTrail,
    KnowledgeClaim,
    KnowledgeEntity,
    KnowledgeGraphView,
    KnowledgeRelationship,
    KnowledgeSnapshot,
    NodeDetail,
    SearchHit,
    TimelineEvent,
)
from app.tools.loader import load_by_name

router = APIRouter(tags=["knowledge"])

# Documents one `analyze` request may extract from. Each chunk is a model call made while the
# request waits, so this is smaller than a mission's limit.
MAX_ANALYZE_DOCUMENTS = 10


class KnowledgeSummary(JarvisModel):
    run_id: str
    store: str
    entities: int
    relationships: int
    claims: int
    conflicts: int
    stats: ExtractionStats
    knowledge_pass_task_id: str | None = None


class AnalyzeRequest(JarvisModel):
    documents: list[str] = Field(min_length=1, max_length=MAX_ANALYZE_DOCUMENTS)


class AnalyzeResponse(JarvisModel):
    """A knowledge base built from documents alone. Nothing is stored."""

    snapshot: KnowledgeSnapshot
    timeline: list[TimelineEvent] = Field(default_factory=list)
    graph: KnowledgeGraphView
    excluded: list[str] = Field(default_factory=list)


class _Run(JarvisModel):
    """What a route needs: the knowledge, the run's findings, and where the knowledge lives."""

    run_id: str
    findings: list[Finding] = Field(default_factory=list)
    knowledge_pass_task_id: str | None = None
    stats: ExtractionStats = Field(default_factory=ExtractionStats)


class KnowledgeNotBuiltError(ApiError):
    def __init__(self, run_id: str) -> None:
        super().__init__(
            "KNOWLEDGE_NOT_BUILT",
            "this mission has no knowledge base: its plan did not need one, or it has not been "
            "built yet",
            status_code=status.HTTP_404_NOT_FOUND,
            run_id=run_id,
        )


async def _open(run_id: str) -> tuple[KnowledgeBase, _Run]:
    """The mission's knowledge base, from the registry, else from Neo4j after a restart."""
    record = get_registry().get(run_id)
    result = record.result if record else None
    store = await get_graph_store()

    if result is not None and result.knowledge is not None:
        run = _Run(
            run_id=run_id,
            findings=list(result.findings),
            knowledge_pass_task_id=result.knowledge_pass_task_id,
            stats=result.knowledge.stats,
        )
        if result.knowledge_store == "neo4j" and store is not None:
            return store.base(run_id), run
        return InMemoryKnowledgeBase(result.knowledge), run

    if record is None:
        if store is not None and await store.exists(run_id):
            snapshot = await store.load(run_id)
            stats = snapshot.stats if snapshot else ExtractionStats()
            return store.base(run_id), _Run(run_id=run_id, stats=stats)
        raise MissionNotFoundError(run_id)
    if not record.is_finished():
        # Not yet, rather than not at all: the client should retry (409, as for reports).
        raise MissionNotFinishedError(run_id, "knowledge base", record.stage.value)
    raise KnowledgeNotBuiltError(run_id)


def _depth(depth: int) -> int:
    return min(max(depth, 0), MAX_DEPTH)


# --- per mission --------------------------------------------------------------------------

PREFIX = "/missions/{run_id}/knowledge"


@router.get(PREFIX, response_model=KnowledgeSummary)
async def summary(run_id: str) -> KnowledgeSummary:
    base, run = await _open(run_id)
    return KnowledgeSummary(
        run_id=run_id,
        store=base.store,
        entities=len(await base.entities()),
        relationships=len(await base.relationships()),
        claims=len(await base.claims()),
        conflicts=len(await base.conflicts()),
        stats=run.stats,
        knowledge_pass_task_id=run.knowledge_pass_task_id,
    )


@router.get(f"{PREFIX}/entities", response_model=list[KnowledgeEntity])
async def entities(run_id: str, name: str = "") -> list[KnowledgeEntity]:
    base, _ = await _open(run_id)
    return await base.find_entity(name) if name else await base.entities()


@router.get(f"{PREFIX}/entities/{{entity_id}}/network", response_model=EntityNetwork)
async def network(
    run_id: str, entity_id: str, depth: int = Query(default=2, ge=0, le=MAX_DEPTH)
) -> EntityNetwork:
    base, _ = await _open(run_id)
    found = await base.network(entity_id, _depth(depth))
    if found is None:
        raise ApiError(
            "ENTITY_NOT_FOUND",
            f"no entity {entity_id} in this mission's knowledge base",
            status_code=status.HTTP_404_NOT_FOUND,
            run_id=run_id,
        )
    return found


@router.get(f"{PREFIX}/relationships", response_model=list[KnowledgeRelationship])
async def relationships(run_id: str, entity_id: str | None = None) -> list[KnowledgeRelationship]:
    base, _ = await _open(run_id)
    return await base.relationships(entity_id)


@router.get(f"{PREFIX}/claims", response_model=list[KnowledgeClaim])
async def claims(
    run_id: str, entity_id: str | None = None, grounded: bool | None = None
) -> list[KnowledgeClaim]:
    base, _ = await _open(run_id)
    found = await base.claims(entity_id)
    return [c for c in found if grounded is None or c.grounded is grounded]


@router.get(f"{PREFIX}/claims/{{claim_id}}", response_model=KnowledgeClaim)
async def claim(run_id: str, claim_id: str) -> KnowledgeClaim:
    base, _ = await _open(run_id)
    found = await base.claim(claim_id)
    if found is None:
        raise ApiError(
            "CLAIM_NOT_FOUND",
            f"no claim {claim_id} in this mission's knowledge base",
            status_code=status.HTTP_404_NOT_FOUND,
            run_id=run_id,
        )
    return found


@router.get(f"{PREFIX}/conflicts", response_model=list[ClaimConflict])
async def conflicts(run_id: str, entity_id: str | None = None) -> list[ClaimConflict]:
    base, _ = await _open(run_id)
    return await base.conflicts(entity_id)


@router.get(f"{PREFIX}/timeline", response_model=list[TimelineEvent])
async def timeline(run_id: str, entity_id: str | None = None) -> list[TimelineEvent]:
    base, _ = await _open(run_id)
    return await base.timeline(entity_id)


@router.get(f"{PREFIX}/timeline/compare", response_model=ClaimComparison)
async def compare(run_id: str, claim_a: str, claim_b: str) -> ClaimComparison:
    base, _ = await _open(run_id)
    found = await base.compare(claim_a, claim_b)
    if found is None:
        raise ApiError(
            "CLAIM_NOT_FOUND",
            "one or both claims are not in this mission's knowledge base",
            status_code=status.HTTP_404_NOT_FOUND,
            run_id=run_id,
            details={"claim_a": claim_a, "claim_b": claim_b},
        )
    return found


@router.get(f"{PREFIX}/investigation", response_model=EntityInvestigation)
async def investigation(run_id: str, name: str = Query(min_length=1)) -> EntityInvestigation:
    base, _ = await _open(run_id)
    found = await base.investigate(name)
    if found is None:
        raise ApiError(
            "ENTITY_NOT_FOUND",
            f"no entity matching {name!r} in this mission's knowledge base",
            status_code=status.HTTP_404_NOT_FOUND,
            run_id=run_id,
        )
    return found


@router.get(f"{PREFIX}/search", response_model=list[SearchHit])
async def search(
    run_id: str, q: str = Query(min_length=1), depth: int = Query(default=1, ge=0, le=MAX_DEPTH)
) -> list[SearchHit]:
    base, _ = await _open(run_id)
    return await base.search(q, _depth(depth))


@router.get(f"{PREFIX}/graph", response_model=KnowledgeGraphView)
async def graph(
    run_id: str,
    focus: str | None = None,
    depth: int = Query(default=2, ge=0, le=MAX_DEPTH),
) -> KnowledgeGraphView:
    """Nodes and links for the 3D explorer: everything, or `focus`'s neighbourhood."""
    base, run = await _open(run_id)
    return await build_view(base, run_id, run.findings, focus=focus, depth=_depth(depth))


@router.get(f"{PREFIX}/nodes/{{node_id}}", response_model=NodeDetail)
async def node(run_id: str, node_id: str) -> NodeDetail:
    """What the hover pop-up shows for one node."""
    base, run = await _open(run_id)
    found = await node_detail(base, node_id, run.findings)
    if found is None:
        raise ApiError(
            "NODE_NOT_FOUND",
            f"no node {node_id} in this mission's knowledge graph",
            status_code=status.HTTP_404_NOT_FOUND,
            run_id=run_id,
        )
    return found


@router.get("/missions/{run_id}/findings/{finding_id}/trail", response_model=FindingTrail)
async def trail(run_id: str, finding_id: str) -> FindingTrail:
    """The claims, documents and entities a finding rests on (A9)."""
    base, run = await _open(run_id)
    finding = next((f for f in run.findings if f.finding_id == finding_id), None)
    if finding is None:
        raise ApiError(
            "FINDING_NOT_FOUND",
            f"no finding {finding_id} in this mission",
            status_code=status.HTTP_404_NOT_FOUND,
            run_id=run_id,
        )
    return await finding_trail(base, finding)


# --- without a mission ----------------------------------------------------------------------


@router.post("/knowledge/analyze", response_model=AnalyzeResponse)
async def analyze(body: AnalyzeRequest) -> AnalyzeResponse:
    """Member 3's standalone use: documents in, a knowledge base out, nothing stored.

    The request waits for extraction, one model call per chunk, which is why the number of
    documents is capped. Nothing is written to Neo4j: a knowledge base with no mission has no run
    to belong to, and storing it would bring back the global store the port removed.
    """
    if not get_knowledge_policy().enabled:
        raise ApiError(
            "KNOWLEDGE_DISABLED",
            "the knowledge layer is disabled in agent.yaml",
            status_code=status.HTTP_409_CONFLICT,
        )
    documents, loaded = load_by_name(body.documents)
    if not documents:
        raise ApiError(
            "NO_READABLE_DOCUMENTS",
            "none of the requested documents could be read",
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            details={"requested": body.documents},
        )
    page_starts = {d.document_id: d.page_starts for d in loaded if d.page_starts}
    snapshot = await KnowledgeExtractor(get_provider()).build(documents, page_starts)
    base = InMemoryKnowledgeBase(snapshot)
    return AnalyzeResponse(
        snapshot=snapshot,
        timeline=await base.timeline(),
        graph=await build_view(base, "analysis", []),
        excluded=[name for name in body.documents if name not in documents],
    )
