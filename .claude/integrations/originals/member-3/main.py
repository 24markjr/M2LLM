from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import db, extractor, resolve, contradictions, timeline, graph, retrieval

app = FastAPI(title="JARVIS Knowledge Layer")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

db.init_db()

class IngestRequest(BaseModel):
    document_id: str
    content: str
    source_document: str
    page: str | int | None = None

@app.post("/ingest")
def ingest(req: IngestRequest):
    result = extractor.extract(req.content)
    resolve.resolve_and_store(result, req.source_document, req.page)
    return result

@app.get("/entities")
def list_entities():
    return db.get_all("entities")

@app.get("/find_entity")
def find_entity(name: str):
    return db.find_entity_by_name(name)

@app.get("/relationships")
def list_relationships():
    return db.get_all("relationships")

@app.get("/relationships/{entity_id}")
def relationships_for_entity(entity_id: str):
    return db.get_relationships_for_entity(entity_id)

@app.get("/claims")
def list_claims():
    return db.get_all("claims")

@app.get("/contradictions")
def get_contradictions():
    return contradictions.detect_contradictions()

@app.get("/timeline")
def get_timeline():
    return timeline.build_timeline()

@app.get("/timeline/compare")
def compare_timeline_events(claim_id_a: str, claim_id_b: str):
    return timeline.compare_events(claim_id_a, claim_id_b)

@app.get("/entity/{entity_id}/network")
def entity_network(entity_id: str, depth: int = 2):
    return graph.get_entity_network(entity_id, depth)

@app.get("/entity/{entity_id}/timeline")
def entity_timeline(entity_id: str):
    return [e for e in timeline.build_timeline() if e["entity"] == entity_id]

@app.get("/evidence/{claim_id}")
def get_evidence(claim_id: str):
    claim = db.get_claim(claim_id)
    if not claim:
        return {"error": "claim not found"}
    return {"claim": claim, "source": {"document": claim["source_document"], "page": claim["source_page"]}}

@app.get("/investigation/{name}")
def investigate(name: str):
    matches = db.find_entity_by_name(name)
    if not matches:
        return {"error": "no entity found"}
    entity = matches[0]
    entity_id = entity["entity_id"]
    return {
        "entity": entity,
        "documents": db.get_sources_for_entity(entity_id),
        "network": graph.get_entity_network(entity_id, depth=2),
        "claims": [c for c in db.get_all("claims") if c["entity"] == entity_id],
        "contradictions": [c for c in contradictions.detect_contradictions()
                            if c["entity"] == entity_id.lower()]
    }

@app.get("/search")
def hybrid_search(q: str, depth: int = 1):
    return retrieval.hybrid_search(q, depth)