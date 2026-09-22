# ADR-002 — PostgreSQL as the primary store

## Status

Accepted — 2026-09-23 (Phase 0)

## Context

JARVIS persists a connected object graph, not documents:

```
agent_runs ─┬─ tasks ─── task_dependencies
            ├─ tool_executions
            ├─ execution_events        (append-only)
            └─ findings ─┬─ evidence
                         └─ verifications
```

Requirements this has to satisfy:

- **Referential integrity.** A finding without its evidence is worse than useless — it is
  exactly the failure mode the project claims to solve. Orphaned rows must be impossible.
- **Semi-structured payloads.** Task input/output and event payloads are schema-versioned
  Pydantic documents of varying shape.
- **Semantic search.** Evidence retrieval (Phase 12) needs vector similarity over document
  chunks, with source locators preserved.
- **Analytical queries.** The evaluation harness (Phase 20) aggregates across runs:
  "evidence coverage per scenario", "replan iterations per model".
- **Concurrency.** The execution engine runs up to `MAX_PARALLEL_TASKS` coroutines writing
  events and tool results simultaneously.

SQLite was the obvious lighter alternative, and was rejected.

## Decision

PostgreSQL 16 as the single primary store, via the `pgvector/pgvector:pg16` image.
SQLAlchemy 2.0 async + asyncpg for access, Alembic for migrations.

## Reason

- **SQLite's write concurrency is a single writer lock.** The execution engine is
  explicitly concurrent; the event sink writes on the hot path of every state transition.
  This is the disqualifying difference, not a preference.
- **`JSONB` with indexing** handles task payloads and event bodies without a second store.
- **pgvector lives in the same database** (ADR-005), so a finding, its evidence row, and
  the embedding of the chunk that evidence points at are joinable in one query. With a
  separate vector database, "which evidence supports this claim" becomes a distributed
  join maintained by hand.
- **Real constraints** — `CHECK (confidence BETWEEN 0 AND 1)`, foreign keys with cascade —
  mean the invariants hold even if a code path forgets them.
- **It is what the system would actually be deployed on.** Building the MVP on SQLite and
  "migrating later" would mean the concurrency behaviour demonstrated is not the behaviour
  that ships.

## Consequences

**Accepted costs**

- Docker is now a hard prerequisite for local development. Mitigated by `scripts/dev-up.*`
  (one command) and `scripts/healthcheck.py` (tells you exactly what is wrong).
- Integration tests need a live database. They are marked `@pytest.mark.integration` and
  CI runs Postgres as a service container.
- Slower cold start than an in-process file.

**Gained**

- The evaluation harness can express its metrics as SQL aggregates rather than Python loops
  over deserialized JSON.
- `agent_runs` cascade-deletes cleanly, so a run can be purged atomically.
- Nothing about the persistence layer has to change between MVP and deployment.

## Revisit if

A contributor cannot run Docker at all. The fallback would be a SQLite-backed
`RunRepository` for unit tests only — never for the execution engine, whose concurrency is
the point.
