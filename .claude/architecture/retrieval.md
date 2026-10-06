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

**`lines` stays the default, by measurement (Experiment 006, below).** A changed chunker re-chunks
unchanged text: each stored document records the chunker that cut it (Phase 41, migration
`00c052316938`); before that, the hash alone said "unchanged" and the old chunks stayed.

## What the live check found (2026-10-06)

Three Aurora reports (18 chunks) ingested into pgvector in 2.3-3.6 s with `nomic-embed-text`; a
re-ingest of an unchanged file took 0.01 s; a search about 0.6 s, or 1.2-1.3 s with the
closest-line step. Paraphrases with no shared keyword found the right sections ("spending went over
what was authorised" -> the over-budget line, "when will the work be finished" -> the milestone
dates).

**Scores cluster high.** Mapped similarities ran 0.71-0.84, and a query nothing answers ("who
supplies the hardware") still scored 0.73. Experiment 006 confirmed it: there is no useful threshold.

## Experiment 006 (Phase 41)

`python -m app.cli eval-retrieval`: 18 fixture documents (text, CSV, Word, Excel) searched together,
20 queries with the exact lines a reader would cite (`.agent/evals/retrieval/queries.yaml`): 6 that
share words with their answer, 10 paraphrases, 4 that nothing answers. A hit counts only at the
exact line. Code `app/evaluation/retrieval.py`; reports
`.agent/evals/experiments/exp-006-retrieval/`. `nomic-embed-text`, 2026-10-06:

| Arm | hit@1 | hit@5 | recall@5 | MRR | passage hit@5 |
|---|---|---|---|---|---|
| lexical (`document_search`) | 0.375 | 0.562 | 0.400 | 0.458 | 0.562 |
| **semantic, line chunks** | **0.562** | **0.938** | **0.680** | **0.729** | 0.938 |
| semantic, Member 2's 600/80 | 0.438 | 0.750 | 0.600 | 0.552 | 1.000 |
| hybrid (rank fusion of lexical and line chunks) | 0.438 | 0.875 | 0.680 | 0.604 | 0.875 |

By kind: lexical found every keyword query in its top 5 (hit@5 1.000, semantic 0.833) but only 3 of
10 paraphrases; semantic found all 10 paraphrases (hit@5 1.000, hit@1 0.700).

**Decisions:**

1. **Line chunks stay the default.** Member 2's 600/80 chunks hold the answer somewhere in the
   passage more often (passage hit 1.000) but cite the right line less often (hit@1 0.438 vs 0.562):
   a long chunk's closest line is more often a neighbour of the answer. A citation that names the
   wrong line is one a reader cannot check, so precision wins.
2. **No hybrid.** Fusing the two rankings (added after the first run, when each search won one kind
   of query) lost to semantic search alone on hit@1 and MRR. Per query: it moved three keyword
   answers up one place (k1, k2, k5), but on paraphrases lexical's wrong-line matches were fused
   above the semantic answer (p2 fell from 1st to 3rd, p9 from 1st to 4th, p10 out of the top 5).
   Not built into the tool.
3. **No `min_score`.** The best-scoring query nothing answers reached 0.802; only 62.5% of answerable
   queries had their first relevant hit above that (31.2% with 600/80 chunks). Any threshold that
   drops non-answers drops real answers, so the API default is 0 and the Documents page shows scores
   rather than filtering.
4. **Missions keep both.** Semantic search is what a mission naming a workspace gets; evaluation
   runs stay lexical, so the agent's baseline is comparable across phases. Making stored retrieval
   the default for every mission would change what the baseline measures and is not done here.

Twenty queries over 18 small documents: a direction, not a benchmark. The semantic numbers were
identical across both runs (deterministic embeddings); lexical is deterministic by construction.
