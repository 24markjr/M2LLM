# ADR-013 — Stored retrieval: pgvector, workspaces, and defaults set by measurement

## Status

Accepted — 2026-10-06 (Phases 40-41)

## Context

Member 2's M2LLM ingested documents, cut them into 600-character chunks with 80 overlapping, embedded
them with Sentence-Transformers, stored the vectors in Qdrant with an in-memory fallback, and searched
within a workspace. JARVIS had a `ContextProvider` seam and a `document_chunks` table with a
`vector(768)` column (ADR-005), and wrote nothing to either: missions found passages by matching
words, line by line.

Two things had to hold whatever was ported. A retrieved passage must be a **citation** the evidence
binder can resolve, not free text. And the evaluation baseline must stay comparable: if the agent's
recall changed underneath it, every later number would describe a different system.

## Decision

**One `ContextStore` protocol, two stores, Member 2's design on this codebase's parts.**

| Member 2 | JARVIS | Why |
|---|---|---|
| Qdrant | pgvector, in the Postgres the findings already live in (D9) | one database; a passage an evidence item points at is a join away |
| Sentence-Transformers | `nomic-embed-text` through `app/llm` (D10) | the model service already running; no second ML runtime; the only way the codebase reaches a model |
| in-memory fallback | `MemoryContextStore`, chosen when the database does not answer | the same, and every answer names its store |
| workspaces | `documents.workspace_id`, default `default`; uploads and missions name one (D11) | as theirs |
| 600/80 chunks | both chunkers: `lines` (ours) and `chars` (theirs), `CONTEXT_CHUNKER` | the default left to measurement |

**Rules that were not in the original:**

1. **Every chunk keeps the line it starts on, and every hit is cited at a line** - the line of its
   chunk closest in meaning to the query, not the chunk's first line (the live check showed first
   lines were headings, which support nothing).
2. **A mission searches only the files it attached**, even when its workspace holds more.
3. **Retrieval never fails a run.** A store or embedding failure falls back to word matching, and the
   tool says which search answered.
4. **Evaluation stays lexical.** Only a mission that names a workspace gets stored retrieval; a
   scenario run passes none (an invariant test checks the runner's source).
5. **Ingest is idempotent** per text hash and chunker; changing `CONTEXT_CHUNKER` re-chunks.
6. **Uploads are indexed after the response.** Embedding a long document took minutes and held the
   upload request with it (2026-10-06).

**Fallback by availability, unlike semantic memory.** Memory refuses to fall back (memory.md) because
two stores would split durable facts. Retrieval may: a passage found in memory is still a line of a
file the mission holds, nothing durable is split, and the answer names its store.

## Defaults, decided by Experiment 006

20 queries over 18 fixture documents, each with the exact lines a reader would cite (keyword,
paraphrase, unanswerable); `python -m app.cli eval-retrieval`, `nomic-embed-text`:

| Arm | hit@1 | hit@5 | MRR | passage hit@5 |
|---|---|---|---|---|
| lexical | 0.375 | 0.562 | 0.458 | 0.562 |
| **semantic, line chunks** | **0.562** | **0.938** | **0.729** | 0.938 |
| semantic, 600/80 chunks | 0.438 | 0.750 | 0.552 | 1.000 |
| hybrid (rank fusion) | 0.438 | 0.875 | 0.604 | 0.875 |

- **Line chunks stay the default.** Member 2's chunks contain the answer more often but cite the
  right line less often; a citation of the wrong line is one a reader cannot check.
- **No hybrid.** Fusion gained a place on three keyword queries and lost more on paraphrases.
- **No similarity threshold.** A query nothing answers scored 0.802, above the first relevant hit of
  37.5% of answerable queries; the API default is 0 and the console shows scores instead.
- **Missions keep both searches.** Making stored retrieval every mission's default would change what
  the baseline measures; it stays opt-in per mission.

## Consequences

- Stored retrieval is a person's tool (the Documents page) and an opt-in for missions; the agent's
  measured behaviour is unchanged by it.
- Twenty queries are a direction, not a benchmark. The experiment is a command and its reports are
  committed, so a larger query set can overturn any of these defaults with numbers.
- Postgres being down makes workspaces temporary, and the console says so.

## References

`.claude/architecture/retrieval.md`; `app/intelligence/context/store.py`,
`app/database/context_store.py`, `app/integrations/context.py`, `app/api/v1/context.py`,
`app/evaluation/retrieval.py`; `.agent/evals/experiments/exp-006-retrieval/`; migrations
`c6e375938463`, `00c052316938`.
