# ADR-005 — pgvector instead of a dedicated vector database

## Status

Accepted — 2026-09-23 (Phase 0)

## Context

Evidence retrieval (Phase 12) needs semantic search over chunks of ingested documents.
The obvious options were a dedicated vector database (Chroma, Qdrant, Weaviate, Pinecone)
or the `pgvector` extension inside the PostgreSQL instance we already run (ADR-002).

The retrieval workload for this MVP is small and specific:

- Corpus: a handful of documents per investigation — hundreds to low thousands of chunks,
  not millions.
- Query pattern: *always* filtered by run and document scope, and the result must carry a
  source locator (`document_id`, page/row, char span) so the evidence binder (Phase 13) can
  resolve a citation to a real location.
- Consumer: a finding's evidence row must point at the exact chunk that was retrieved.

## Decision

Use `pgvector` in the same PostgreSQL database that holds runs, tasks, findings and
evidence. The image is `pgvector/pgvector:pg16`; the extension is created both by
`scripts/sql/init/001-extensions.sql` (first container init) and idempotently by Alembic
migration 0001 (any other database).

Embeddings are `vector(768)` by default, matching `nomic-embed-text`; the dimension is
configurable via `EMBEDDING_DIM`.

## Reason

- **Evidence integrity is the project's core claim.** With a separate vector store, the
  link from `evidence.source_id` to the chunk that produced it is a cross-system reference
  that nothing enforces. In one database it is a foreign key. A dangling evidence pointer
  becomes impossible rather than merely unlikely.
- **Filtered search is the normal case here, not the exception.** Every retrieval is scoped
  to a run's documents. In Postgres that is a `WHERE` clause on an indexed column combined
  with the vector ordering. Dedicated stores handle metadata filtering well now, but there
  is no advantage to gain and a join to lose.
- **Scale does not justify the second system.** pgvector with an HNSW index is comfortable
  well past this MVP's corpus size. Introducing a second database for a few thousand
  vectors would be infrastructure theatre.
- **One backup, one connection pool, one migration path, one healthcheck.**

## Consequences

**Accepted costs**

- At very large corpora (millions of vectors), a purpose-built store would outperform this.
  Not this project's problem, and the retrieval interface is designed so it would not have
  to be a rewrite.
- Index tuning (`hnsw` parameters, `ef_search`) is manual rather than managed.

**Gained**

- `search()` returns chunks with their locators in a single query, joined to the documents
  table — which is exactly the shape the evidence binder needs.
- The evaluation harness can compute evidence coverage in SQL across runs.

## Boundary that protects this

Retrieval is consumed through the `ContextProvider` protocol (Phase 12), with the local
pgvector implementation as the default and Member 2's M2Context service as a drop-in
alternative. Swapping the retrieval backend touches `app/integrations/` and nothing else,
so this decision is reversible at one seam.
