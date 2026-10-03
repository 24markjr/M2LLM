# ADR-010 — Neo4j for the knowledge graph, optional, behind one protocol

## Status

Accepted — 2026-10-03 (Phase 29)

## Context

Member 3's knowledge graph kept entities, relationships and claims in SQLite and rebuilt a NetworkX
graph from them on every request. Phase 28 ported the logic into a per-run, in-memory knowledge
base. Three things want a real graph store:

1. **Neighbourhood queries** (K5, K10). "Everything within two hops of Shipment 4821" is a path
   query, which a graph database answers from an index, and the original answered by rebuilding the
   whole graph.
2. **Cross-investigation memory** (Phase 33, A14). "Rahul Sharma, as seen across every past
   investigation" is the query a per-run in-memory store cannot answer at all.
3. **The 3D explorer** (Phase 32) wants nodes and edges, including conflicts as edges between claims.

The owner asked for Neo4j explicitly (2026-10-03), and when asked whether it should be required or
optional answered that Docker now works and Neo4j would be good (decision D1).

PostgreSQL is already in the stack (ADR-002), and a graph could be modelled there with recursive
CTEs.

## Decision

**Neo4j 5 Community is the default knowledge-graph store (`GRAPH_STORE=neo4j`), and it is optional.**

- `docker compose up -d neo4j` starts it, with heap and page cache sized for a laptop that also
  runs Ollama (512 MB / 256 MB).
- `app/integrations/neo4j_store.py` is the only module that imports the driver (enforced by test).
  Everything else depends on the `KnowledgeBase` protocol.
- When Neo4j is unreachable, runs use the in-memory store and log `graph_store_degraded` once per
  process. A failed write degrades the same way. **Neo4j never fails a run.**
- Every node carries its `run_id` and every query filters on it, so one database holds many runs
  without any of them seeing another.

## Why Neo4j rather than PostgreSQL

- The queries this layer exists for are path queries. `(c)-[:RELATES*1..2]-(n)` is one line of
  Cypher, against a recursive CTE with cycle handling in SQL.
- It is what the owner asked for, and the person demonstrating the system can open
  <http://localhost:7474> and look at an investigation's graph directly.
- Cross-run entity resolution (Phase 33) is a `MERGE` on a normalised name in Cypher.

## Why optional rather than required

- Docker on this machine (Windows 11 Home, WSL2) was down for most of the project. A demo that needs
  Neo4j fails the day Docker does.
- `python -m app.cli investigate` must keep working with only Ollama, as it did with Postgres
  (rule 9 of the integration plan).
- CI unit jobs run with no services at all.

## Why one protocol, with the analysis shared

The in-memory store is the fallback a run gets when Neo4j is down. If the two stores answered
differently, a run's report would depend on whether a container was up. So:

- **One test suite runs against both stores** (`tests/unit/test_knowledge_stores.py`). In CI the
  integration job starts Neo4j and fails if the Neo4j half skips.
- **Analysis is shared Python, not reimplemented in Cypher.** Timeline order, search scores, entity
  ranking and the investigation aggregate run on data read from either store. Cypher does storage,
  lookup and the neighbourhood traversal.
- Measured (2026-10-03): a live extraction of Member 3's sample stored in Neo4j answered entities,
  claims, conflicts, timeline, search and investigation **identically** to the in-memory store.

## Consequences

- The protocol became async (Phase 29), because the Neo4j driver is. The in-memory store implements
  the same async methods.
- A new service in `docker-compose.yml`, a dependency (`neo4j>=5.20`), five settings
  (`GRAPH_STORE`, `NEO4J_URI`, `NEO4J_USER`, `NEO4J_PASSWORD`, `NEO4J_DATABASE`), a healthcheck row,
  and a CI service.
- The driver belongs to the event loop that created it, so the store is cached per loop. The API
  closes it on shutdown.
- Node keys (which would also enforce that `run_id` exists) are Enterprise-only. Composite
  uniqueness constraints are used instead, and the writer always sets `run_id`.
