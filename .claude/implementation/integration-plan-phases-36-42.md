# Integration plan — Phases 36–42: completing Members 2, 3 and 4

**Status:** Drafted 2026-10-05 after an as-built review of the three teammates' reports against this
codebase. Phases 36-39 done the same day. D7-D11 taken as recommended when the owner said to
proceed with Phase 38 (to be overridden if wanted). D8 and D12 settled by Phase 39 (ADR-012).

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
| D12 | Speech-to-text for video and audio (raised in Phase 38) | An optional extra (`faster-whisper`, local, no model service), like OCR; until then a video's text is a subtitle file of the same name |

---

## Phases

| # | Phase | Covers | Size | Depends on | Status |
|---|---|---|---|---|---|
| 36 | Member 3's missing screens | Hybrid search, timeline, all contradictions, the investigate card - one workbench tied to the graph | M | - | **DONE** 2026-10-05 |
| 37 | Member 4's answer evaluator, wired in | The final report checked sentence by sentence, deterministically | S | - | **DONE** 2026-10-05 |
| 38 | Member 2 (A): formats, provenance, adding files | One parser per file type (Word, Excel, CSV, PDF, text, subtitles, images, video); provenance; New Mission adds files, typed context and earlier uploads | M | D7 | **DONE** 2026-10-05 |
| 39 | Seeing and hearing | Read (OCR: images, scans, frames), seen (a vision model, `[seen]` lines, weaker evidence), heard (speech-to-text: video, audio); cached once per file | L | 38 | **DONE** 2026-10-05 |
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

---

### Phase 37 — Member 4's answer evaluator, wired in

**Goal:** the report's model-written prose checked sentence by sentence, with no model call.

**As built (2026-10-05).** Synthesis places every fact; the model writes two paragraphs (the
executive summary and the reasoning). Each of their sentences is checked against the lines the
report's verified and uncertain findings cite, with Member 4's `evaluate_answer` as ported, plus the
specifics check (a date or figure no cited line contains, a number where a date belongs). The
report keeps the prose as written and carries a `NarrativeCheck` per paragraph beside it.

| Where | What |
|---|---|
| `synthesis/grounding.py` | The check (pure). Member 4's overall rule is reused unchanged (`trust/answer.py:overall_status`, factored out); one case their rule never met (a sentence downgraded by the specifics check) is stated |
| `FinalReport.narrative_checks` | `SentenceCheck`: sentence, status, reasoning, ungrounded values |
| `REPORT_EVALUATED` | Per-paragraph verdicts and how many sentences were not supported. EventType 39 -> 40 |
| Report Markdown and terminal text | A "How grounded the narrative is" / "NARRATIVE CHECK" section listing what was not supported |
| Mission page | A verdict badge under each narrative paragraph; weak sentences listed; each value not in evidence **links to the knowledge graph searching for it** (`#/mission/{id}/graph?q=`) |

**Not built: `eval --with-report`.** The evaluation suite skips synthesis to save a model call per
scenario. The opt-in mode was planned to report the check per scenario; it was left out to keep the
phase small. Every API and CLI mission gets the check.

**Verified:** 9 new backend tests (the check, synthesis with the event, both renderings, the
unchanged overall rule), 1 new Vitest assertion group; mypy, ruff, tsc, build. The database-backed
integration tests skipped in the final run because Docker was down; none touch this phase's code.

---

### Phase 38 — Member 2 (A): every file type, and adding files to a mission

**Owner's additions when approving it (2026-10-05):** documents, Excel, CSV, XLSX, any kind of file,
image or video, one parser per extension where needed; an option to add files and to type context;
all of it in the New Mission form.

**As built.**

| Piece | What |
|---|---|
| `app/tools/formats.py` | **The format registry**: one entry per family, its extensions, its parser and how it becomes lines. The upload endpoint's accepted types, the console's file picker (`GET /documents/formats`) and `load_document` all read it |
| Parsers | Text (`.txt .md .json .log`), table (`.csv .tsv`), **spreadsheet** (`.xlsx .xlsm`: each sheet a page, one row per line, computed values), **Word** (`.docx`: paragraphs *and tables* in order - Member 2's dropped tables), PDF, **subtitles** (`.srt .vtt`: one timed cue per line), **image** (8 extensions: size, format, EXIF orientation - Member 2's behaviour), **video** (6 extensions: the transcript from a same-named subtitle file) |
| No text yet | An image, or a video without a transcript, is accepted and kept but `has_text=False`: a mission excludes it and logs why, the picker shows it as "kept, not attached until it has text". Text from images is Phase 39 (OCR); from speech, D12 |
| Provenance | Every upload reports its parser and SHA-256 (Member 2's provenance log) and is logged with them |
| Uploads | Streamed to a temporary file and renamed when complete (was: buffered in memory). 25 MB, or 500 MB for video. `GET /documents` lists earlier uploads |
| New Mission | A document picker: attached documents with what each parsed as (kind, size, lines or pages, an injection warning); **Add files** (picker and drag-and-drop); **Type or paste context** (saved as a named `.txt`, cited like any document); **Earlier uploads**; **Examples**; "how each type is read" |
| Knowledge page | Uses the same picker, so an analysis can read uploads and typed context too |

**Defects found:** BUG-023 (no mission could use an uploaded file) and BUG-024 (`.agent/uploads/` was
not git-ignored). Both fixed; see the bug log.

**Not in this phase:** OCR (39), speech-to-text (D12), storing hashes in the `documents` table (40,
with stored retrieval).

**Verified:** 19 new backend tests (every parser on generated files, the upload API, the BUG-023
regression), 3 new Vitest tests; mypy, ruff, tsc, build. Docker was down: the 57 database tests
skipped, none touching this phase.

---

### Phase 39 — Seeing and hearing (was: Member 2 (B), OCR)

**What the owner asked for:** *"our AI needs to understand not only text but also the content
itself."* So the phase grew from OCR to three ways of understanding a file, decided in ADR-012:

- **Read** (OCR, RapidOCR with PaddleOCR's models): text in images, scanned PDF pages, video frames.
- **Seen** (a local vision model, `qwen2.5vl:3b`, through `app/llm/`): what an image or frame shows,
  as `[seen]` lines - an account, weaker evidence: never grounds a knowledge value, and a finding
  resting only on it is `PARTIALLY_SUPPORTED` (`DESCRIBED_ONLY`).
- **Heard** (faster-whisper, CPU): what is said in video and audio, timed. A person's transcript is
  preferred when present.

**D8 revised:** OCR as recommended, *and* a vision model - kept apart from what was read, which was
the reason D8 had excluded one. **D12 answered:** speech-to-text added, local.

**As built:** `app/tools/media.py` (the engines and the cache), `formats.prepare` (run before uploads,
missions, analyses, CLI and evaluation read a file), the `vision` role and `VISION_MODEL`,
`CompletionRequest.images`/`model`, `prompts/vision.md`, an audio format family, the
`DESCRIBED_ONLY` rule, the grounding rule, the upload response's `understood` line, the optional
`backend[media]` extra (CI installs it), media understanding off by default in tests.

**Verified:** 14 new tests (real OCR on generated images, a scanned PDF, a generated video; the echo
provider as the vision model; speech stubbed except the decoder); the full suite with Docker up, 967
passed and none skipped; **one live check** with the real models (development log): a delivery note
read and seen in 15.5 s, a spoken sentence heard in 2.4 s. The live check found BUG-025.
