# JARVIS — Knowledge Graph & Retrieval Intelligence Layer

**Owner:** Member 3
**Role:** Answers "how is this information connected?" — takes extracted document text, builds a connected knowledge graph, detects contradictions across sources, and exposes queryable APIs for the rest of the JARVIS system.

---

## What this module does

Given plain text extracted from documents (by Member 2's ingestion pipeline), this module:

1. Extracts entities (people, organizations, locations, dates, shipments, etc.) and relationships between them using a local LLM
2. Resolves entities across documents — the same name mentioned in multiple files is merged into one entity, not treated as separate mentions
3. Stores everything as a queryable knowledge graph (NetworkX, built on top of SQLite)
4. Detects contradictions — when two sources state different values for the same fact about the same entity
5. Builds timelines with explicit before/after/same-time relationships between dated events
6. Supports hybrid search — combining direct entity matching, graph traversal, and keyword matching, with an explainable score for every result
7. Exposes all of the above as a REST API for Member 1 (planner/agent) to call

---

## Architecture

```
Text chunk (from Member 2)
        ↓
   /ingest endpoint
        ↓
  extractor.py  →  local LLM (Ollama) pulls out entities, relationships, claims
        ↓
  resolve.py    →  merges duplicate entities, links relationships/claims via entity IDs
        ↓
  db.py         →  stores in SQLite (entities, relationships, claims tables)
        ↓
  ┌─────────────┬──────────────┬───────────────┬──────────────┐
  graph.py    contradictions.py  timeline.py    retrieval.py
  (NetworkX   (finds conflicting (before/after   (hybrid search +
   traversal)  claims)            event ordering) explainable ranking)
  └─────────────┴──────────────┴───────────────┴──────────────┘
        ↓
   main.py — FastAPI endpoints exposing all of the above
        ↓
   dashboard.html — browser UI for testing/demoing
```

---

## File structure

```
jarvis-member3/
├── main.py              # FastAPI app — all API endpoints
├── db.py                 # SQLite storage + entity resolution queries
├── extractor.py           # LLM-based entity/relationship/claim extraction
├── resolve.py               # Entity deduplication + ID linking
├── graph.py                  # NetworkX graph construction + traversal
├── contradictions.py          # Contradiction detection across claims
├── timeline.py                 # Timeline building + before/after comparison
├── retrieval.py                 # Hybrid search with explainable scoring
├── dashboard.html                # Browser UI (search, graph view, contradictions)
├── sample_data.json               # Sample document chunks for testing
├── load_sample.py                  # Script to feed sample_data.json into /ingest
└── jarvis_knowledge.db               # SQLite database (created on first run)
```

---

## Setup

1. **Install dependencies:**
```bash
python3 -m venv .venv
source .venv/bin/activate
pip install fastapi uvicorn requests pydantic networkx
```

2. **Install and run Ollama** (local LLM for extraction):
```bash
# Download from https://ollama.com, then:
ollama pull qwen2.5:7b
```
Ollama runs automatically in the background once installed.

3. **Start the API:**
```bash
uvicorn main:app --reload
```
Runs at `http://127.0.0.1:8000`. Interactive API docs at `http://127.0.0.1:8000/docs`.

4. **Load sample data** (optional, for testing):
```bash
python3 load_sample.py
```

5. **Open the dashboard:** open `dashboard.html` directly in a browser.

---

## API Reference

| Endpoint | Method | Description |
|---|---|---|
| `/ingest` | POST | Accepts a document chunk (`content`, `source_document`, `page`), extracts and stores entities/relationships/claims |
| `/entities` | GET | List all known entities |
| `/find_entity?name=` | GET | Find entities by partial name match |
| `/relationships` | GET | List all relationships |
| `/relationships/{entity_id}` | GET | Get relationships for one entity |
| `/claims` | GET | List all claims |
| `/contradictions` | GET | List all detected contradictions system-wide |
| `/timeline` | GET | Get all dated events, sorted chronologically, with before/after/same-time labels |
| `/timeline/compare?claim_id_a=&claim_id_b=` | GET | Compare two specific claims' temporal relationship |
| `/entity/{entity_id}/network?depth=` | GET | Get an entity's connected graph (nodes + edges) within N hops |
| `/entity/{entity_id}/timeline` | GET | Get dated events for one specific entity |
| `/evidence/{claim_id}` | GET | Get a single claim's source document and page |
| `/investigation/{name}` | GET | **Main endpoint.** Given a name, returns entity info, source documents, connected network, claims, and contradictions in one response |
| `/search?q=&depth=` | GET | Hybrid search — combines entity matching, graph traversal, and keyword matching; returns ranked results with explainable scoring |

### Example: full investigation

```bash
curl "http://127.0.0.1:8000/investigation/Shipment%204821"
```

Returns entity details, every document that mentions it, its full connected network, every claim made about it, and any contradictions found — each with source document and page number.

### Example: hybrid search

```bash
curl "http://127.0.0.1:8000/search?q=Rahul%20warehouse"
```

Returns claims ranked by relevance, each with a score and an explanation (e.g. `"direct entity match"`, `"keyword match: warehouse"`, `"connected via graph"`) — no black-box confidence numbers, every score is traceable to a specific reason.

---

## Design decisions worth knowing

- **SQLite, not PostgreSQL:** sufficient for MVP and independent development; can be swapped later if the team integrates into a shared backend.
- **NetworkX, not a graph database:** graph is rebuilt from SQLite on each query — simpler to maintain, no separate database to keep in sync, fine at this data scale.
- **Contradiction detection is rule-based, not ML-based:** groups claims by (entity, attribute) and flags disagreement in value. Deliberately does not decide which source is "correct" — it surfaces the conflict with full evidence and lets a human (or downstream reasoning layer) judge.
- **Hybrid search combines entity + graph + keyword matching, not full semantic/vector search:** true semantic search requires embeddings, which is Member 2's responsibility (M2LLM/multimodal context layer). This module's retrieval is entity-and-relationship-aware rather than meaning-aware — a deliberate, documented scope boundary for the MVP.
- **Modality-agnostic by design:** this module only ever consumes plain text plus a source label and page/timestamp reference. Whether that text originated from a PDF, an image (via OCR), audio (via transcription), or video, is irrelevant to this layer — that conversion is entirely Member 2's responsibility. No changes are needed here regardless of what Member 2's pipeline outputs, as long as it arrives as text.

---

## Known limitations (honest, not hidden)

- Extraction quality depends on the LLM's output — inconsistent phrasing in source text can occasionally cause the same fact to be missed or a relationship to not be cleanly extracted.
- Contradiction detection catches direct attribute conflicts (same entity, same attribute, different values). It does not yet catch indirect/negation-based contradictions (e.g. one document naming a different person for the same role without using the same attribute name).
- Evidence ranking uses transparent rule-based scoring (entity match, graph connection, keyword overlap, source presence) rather than a calibrated statistical relevance model.