# Integration plan — Phases 36–42: completing Members 2, 3 and 4

**Status:** Drafted 2026-10-05 after an as-built review of the three teammates' reports against this
codebase. Phase 36 approved and started the same day; decisions D7-D11 still open.

**Why this plan exists.** Phases 25-35 ported Members 3 and 4. A review of their own build reports
found what that left out: three of Member 3's dashboard views had an API but no screen, Member 4's
answer evaluator was ported but not called, and Member 2 (M2LLM, document ingestion) was never in
scope. This plan covers all three.

**A rule from the owner for every phase:** *everything is interrelated*. A new view links to the
existing ones and drives them; nothing is a standalone screen.

**Carried over from Phases 25-35:** one commit per phase, a pause after each, everything documented,
defaults decided by measurement. **Testing:** fast checks (tests, typecheck, build) for routine work;
a live model or browser run only when a phase's acceptance needs a measurement, once.

---

## Correction to the review

The review said JARVIS has "pgvector search". It does not: `LocalContextProvider`
(`app/intelligence/context/manager.py`) keeps its embeddings in memory, and its docstring says moving
to pgvector was deferred. The `document_chunks` table and its vector column exist, unused. Phase 40
accounts for that.

## Decisions needed (before Phase 38)

| # | Question | Recommendation |
|---|---|---|
| D7 | Port Member 2 like Members 3 and 4 (re-implemented in-process, same logic, typed, tested, originals archived)? | Yes (ADR-009's reasons) |
| D8 | OCR engine | PaddleOCR (theirs) as an optional extra (`backend[ocr]`), degrading cleanly when absent. Not a vision LLM: a model reading a scan can invent text, which defeats grounding |
| D9 | Vector store | pgvector (ADR-005) with their in-memory fallback idea; not Qdrant |
| D10 | Embeddings | Keep `nomic-embed-text` via Ollama; not Sentence-Transformers (PyTorch, ~2 GB; and the LLM stays behind `app/llm/`) |
| D11 | Workspaces | `workspace_id` on uploads and retrieval (default `default`); a mission may name a workspace as its document scope |

---

## Phases

| # | Phase | Covers | Size | Depends on | Status |
|---|---|---|---|---|---|
| 36 | Member 3's missing screens | Hybrid search, timeline, all contradictions, the investigate card - one workbench tied to the graph | M | - | **DONE** 2026-10-05 |
| 37 | Member 4's answer evaluator, wired in | The final report checked sentence by sentence, deterministically | S | - | TODO |
| 38 | Member 2 (A): formats and provenance | DOCX (paragraphs and tables), XLSX (sheets as pages), images; file hash, parser and OCR flag stored | M | D7 | TODO |
| 39 | Member 2 (B): OCR | Scanned PDFs and images; OCR'd text marked to the evidence; low confidence never makes a conflict | M-L | 38, D8 | TODO |
| 40 | Member 2 (C): stored, workspace-scoped retrieval | pgvector with an in-memory fallback; `/context/ingest` and `/context/retrieve`; their 600/80 chunker beside ours, chosen by measurement | L | D9-D11 | TODO |
| 41 | Evaluation and hardening | Three new scenarios (14), recall@k, Experiment 006 (chunking), repeated runs with spread, CI, invariants, a new baseline | M | 36-40 | TODO |
| 42 | Documentation and handover | README, contribution (Member 2), port inventory, ADR-012 (OCR), ADR-013 (retrieval), demos, clean clone with and without OCR | S | 41 | TODO |

**Minimum, if time runs short:** 36, 38, 39.

**Deliberately not planned:** Member 2's vision-language interface (theirs raises "not implemented"),
carrier tracking (out of scope in their own report), Sentence-Transformers and Qdrant (unless D9/D10
are overruled).

---

### Phase 36 — Member 3's missing screens

**Goal:** everything Member 3's dashboard showed is in Mission Control, and connected.

**As built (2026-10-05).**

| Piece | What it does | Leads to |
|---|---|---|
| Workbench, **Search** tab | Free text, Member 3's hybrid ranking with a score badge and the reasons for each hit | the hit's claim selected in the graph; its entity's card |
| Workbench, **Timeline** tab | Dated claims in order, each tagged before / same time / order unknown; a missing year said, an inferred one marked; tick two to compare | the event's claim selected; its entity's card |
| Workbench, **Contradictions** tab | Every conflict with every side and its citations | every side lit at once (a "spotlight", like a finding's evidence trail); its entity's card; each side's claim |
| **Investigate card** (an entity's side panel) | Member 3's `/investigation`: documents, contradictions, claims, timeline, connections | each document node, claim, contradiction, timeline event and connected entity; the workbench search; Memory |
| Graph selection | - | narrows the timeline and contradictions to the selected entity, with "all entities" |
| Entry search box | Enter with no matching entity | searches every claim in the workbench |
| Memory | an entity's missions | "(graph)": that mission's graph opened on the entity (`#/mission/{id}/graph?focus=`) |
| Investigate card -> Memory | - | `#/memory?entity=` opens Memory with the entity looked up |

An analysis (`#/knowledge`, nothing stored) gets the card, timeline and contradictions built in the
browser from its own response; search and date comparison need a stored base and say so.

**Verified:** Vitest (32: 10 new, on where each click leads), strict typecheck, production build.
**Not verified in a browser** for this phase: the owner asked for no repeated live runs; the views
are wired through the same, tested functions.
