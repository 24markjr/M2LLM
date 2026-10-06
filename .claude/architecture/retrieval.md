# Stored, workspace-scoped retrieval (Phase 40)

Member 2's ingest-and-search (M2LLM: chunk, embed, store in Qdrant with an in-memory fallback, search
within a workspace), ported in-process (D7) onto this codebase's stores: pgvector (D9, ADR-005) and
the embedding model Ollama serves, `nomic-embed-text` (D10), scoped by workspace (D11).

Code: `app/intelligence/context/store.py` (chunkers, the `ContextStore` protocol, the memory store),
`app/database/context_store.py` (pgvector), `app/integrations/context.py` (store choice, ingest,
search, the mission's retriever), `app/api/v1/context.py`, the tool `context_retrieval`
(`app/tools/builtin.py`). UI: `#/documents` (`DocumentsPage.tsx`), New Mission's workspace field.

## The flow

```
upload (?workspace=w) ─┐
POST /context/ingest ──┼─> parse (format registry) -> chunk -> embed (32 per call) -> store
mission (workspace_id) ┘        skipped when the text's SHA-256 is unchanged

POST /context/retrieve ─┐
context_retrieval tool ─┴─> embed query -> nearest chunks in the workspace (cosine)
                              -> each cited at its line closest to the query
```

## Rules

1. **A passage is a citation.** Every chunk keeps the line it starts on, whichever chunker made it,
   and every hit is cited at a line (`report.txt:r9`) the evidence binder resolves, never as free
   text.
2. **Cited at the closest line, not the first.** Measured on the Aurora reports with the real model:
   the first line of a matching chunk was usually its heading ("2. CURRENT STATUS"), which supports
   nothing. After the search, the lines of the top hits are embedded in one call and each hit is
   cited at its line most similar to the query (`r9`: "The financial team records expenditure above
   the original approved project budget."). The chunk's text stays the passage, for context.
3. **A mission searches only its own documents.** The workspace may hold more; the tool restricts the
   search to the files the mission attached, and drops anything else.
4. **Never failing a run.** Store down, embedding model down, nothing found: the tool answers with
   the lexical search and says so (`provider: local`, `note`). A mission whose workspace ingest
   fails runs with lexical recall (`workspace_ingest_failed` in the log); an upload whose ingest
   fails is still stored and usable (`ingested: null`, `note`).
5. **The store answering is always named** (`store: pgvector` or `memory`), in every API response
   and as the tool's `provider`.
6. **Evaluation stays lexical.** Only missions that name a workspace get stored retrieval; scenario
   runs pass none, so the baseline stays comparable. Experiment 006 (Phase 41) measures the switch.

## pgvector, or memory - and why a fallback here

pgvector when the database answers (probed once per process, like run persistence), the in-memory
store otherwise. Semantic memory refuses to fall back ("chosen by configuration, never by
availability", `memory.md`) because two stores would split durable facts. Retrieval may: a passage
found in memory is still a line of a file the mission holds, nothing durable is split, and the
answer names its store. The memory store is lost on restart and the Documents page says so.

Both stores score alike: the memory store maps cosine similarity to [0, 1] as `(cos + 1) / 2`; the
database's cosine distance `d = 1 - cos` becomes `1 - d / 2`. One test suite runs against both
(`tests/integration/test_context_store.py`).

Tables (since Phase 3, written from Phase 40): `documents` (now with `workspace_id`, `sha256` of the
parsed text, `parser`; unique on workspace and document) and `document_chunks` (`row`, `page`, the
text, `vector(768)`). Replacing a document deletes the row; its chunks cascade.

## Two chunkers

| `CONTEXT_CHUNKER` | What | Citation |
|---|---|---|
| `lines` (default) | Up to four lines, or to a blank line | the chunk's first line |
| `chars` | Member 2's: 600 characters, 80 repeated, nudged to a word start | the line of its first kept character |

Which is the default is decided by Experiment 006, as every default since Phase 34.

## What the live check found (2026-10-06)

Three Aurora reports (18 chunks) ingested into pgvector in 2.3-3.6 s with `nomic-embed-text`; a
re-ingest of an unchanged file took 0.01 s; a search about 0.6 s, or 1.2-1.3 s with the
closest-line step. Paraphrases with no shared keyword found the right sections ("spending went over
what was authorised" -> the over-budget line, "when will the work be finished" -> the milestone
dates).

**Scores cluster high.** Mapped similarities ran 0.71-0.84, and a query nothing answers ("who
supplies the hardware") still scored 0.73. A `min_score` of 0.5 therefore filters nothing; a useful
threshold is a measurement for Experiment 006, not a guess made here.
