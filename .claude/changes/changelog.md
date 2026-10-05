# Changelog

All notable changes to JARVIS (Member 1 — intelligence & agent orchestration).
Newest first. Categories: Added · Changed · Fixed · Removed · Known Issues.

---

## 2026-10-05 - Phase 39: seeing and hearing

### Added

- `app/tools/media.py`: images, scanned PDFs, video and audio understood, once per file, cached
  by SHA-256 (`.agent/media-cache/`): text **read** (OCR, PaddleOCR's models via RapidOCR), speech
  **heard** (faster-whisper, CPU), and what they show **seen** by a local vision model
  (`qwen2.5vl:3b`, the new `vision` role) as `[seen]` lines
- Video as a timeline (speech or a person's transcript, on-screen text, what sampled frames show;
  at most 8 frames); an audio family (`.mp3 .wav .m4a .ogg .flac .aac`); OCR for PDF pages with no
  text layer
- `[seen]` is weaker evidence: never grounds a knowledge value; a finding resting only on it is
  `PARTIALLY_SUPPORTED` with the new `DESCRIBED_ONLY` issue
- `CompletionRequest.images` and `.model`; `VISION_MODEL`, `MEDIA_UNDERSTANDING`, `WHISPER_MODEL`
  and frame/length bounds in settings; `prompts/vision.md` v1
- Upload response: `understood` (lines read, segments heard, lines seen and by which model)
- `backend[media]` optional extra; CI installs it
- ADR-012; 14 tests (`test_media.py`), 2 updated in `test_api_documents.py`

### Fixed

- **BUG-025**: speech recognition failed on every file (faster-whisper vs PyAV 19); audio now
  decoded by our code
- **BUG-026**: one failed vision call discarded what had been read from a video

### Changed

- Tests never reach a real vision model: media understanding is off by default in tests

### Measured (one live check)

- A delivery-note image: 5 lines read, 10 seen, 15.5 s. OCR read the crate's "4821" as "4881"
  where the vision model said "4821" - kept apart and labelled, as ADR-012 argues
- A 7-second spoken sentence: transcribed in 2.4 s, "forty-eight twenty-one" heard as "48-21"

---

## 2026-10-05 - Phase 38: every file type, and adding files to a mission

### Added

- `app/tools/formats.py`: the format registry and one parser per family - text, CSV/TSV,
  **Excel** (`.xlsx`, `.xlsm`, each sheet a page), **Word** (`.docx`, tables included), PDF,
  **subtitles** (`.srt`, `.vtt`, timed cues), **images** (8 types, described; text needs OCR) and
  **video** (6 types, text from a same-named subtitle file)
- Upload provenance: parser and SHA-256 per file; `has_text` and a note for files with no text yet
- `GET /api/v1/documents/formats` (what the engine reads) and `GET /api/v1/documents` (earlier
  uploads); OpenAPI 36 -> 37 paths
- New Mission's **document picker**: add files (picker and drag-and-drop), **type or paste context**
  (saved as a named document), reuse earlier uploads, examples, and what each file parsed as. The
  Knowledge page uses the same picker
- Dependencies: `python-docx`, `openpyxl`, `Pillow`
- Tests: `test_formats.py` (12), `test_api_documents.py` (7, the endpoint's first), Vitest 3

### Changed

- Uploads stream to a temporary file and are renamed when complete (were buffered in memory);
  video may be up to 500 MB
- A mission excludes a file with no text yet and logs why

### Fixed

- **BUG-023**: no mission could use an uploaded file (`resolve_document` never searched uploads)
- **BUG-024**: `.agent/uploads/` was not git-ignored

---

## 2026-10-05 - Phase 37: Member 4's answer evaluator checks every report

### Added

- `app/intelligence/synthesis/grounding.py`: the report's two model-written paragraphs checked
  sentence by sentence against the lines its findings cite (Member 4's `evaluate_answer`), plus the
  specifics check (values no cited line holds; a number where a date belongs)
- `FinalReport.narrative_checks` (`NarrativeCheck`, `SentenceCheck`); `REPORT_EVALUATED` event
  (EventType 39 -> 40)
- Report Markdown and terminal output: what in the narrative was not supported, and why
- Mission page: a verdict badge under each narrative paragraph; each unsupported value links to the
  knowledge graph searching for it (`#/mission/{id}/graph?q=`, new); the explorer opens its search
  tab on `?q=`
- 9 backend tests (`test_report_grounding.py`), Vitest for the new link

### Changed

- `trust/answer.py`: Member 4's overall rule factored out (`overall_status`), unchanged
- The mission passes the line text it already builds for verification into synthesis
- `docs/openapi.json` regenerated (the report schema gained a field)

### Not built

- `eval --with-report` (planned, left out to keep the phase small; the suite skips synthesis)

---

## 2026-10-05 - Phase 36: Member 3's missing screens, interrelated

### Added

- `components/graph3d/Workbench.tsx`: Member 3's **hybrid search** (score badge and reasons),
  **timeline** (before / same time / order unknown, missing and inferred years said; pick two to
  compare) and **all contradictions** (every side with its citations), as tabs under the graph
- `components/graph3d/InvestigateCard.tsx`: an entity's **investigate card** (Member 3's
  `/investigation`): documents, contradictions, claims, timeline, connections
- `components/graph3d/investigation.ts` (pure, 10 tests) and `access.ts` (API for a mission, the
  browser for an analysis)
- API client and types for `knowledge/search`, `/timeline`, `/timeline/compare`, `/conflicts`,
  `/investigation`; `AnalyzeResponse` now typed with its snapshot and timeline
- `.claude/implementation/integration-plan-phases-36-42.md`

### Changed - everything linked

- Any row selects or lights the graph; any entity name opens its card; a contradiction lights all
  of its sides (the evidence-trail highlight, generalised to a "spotlight")
- The graph's selection narrows the timeline and contradictions ("all entities" switch)
- The entity search box falls through to the claim search when no entity matches
- Memory <-> graph: `#/memory?entity=` opens Memory on an entity; an entity's missions link to
  `#/mission/{id}/graph?focus=`, which opens the graph on it
- A claim's panel links to its entity

### Verified

- Vitest 32 (10 new), `tsc -b`, `npm run build`. Not walked through in a browser this phase (the
  owner asked for no repeated live runs)

---

## 2026-10-05 - Phase 35: documentation and handover

### Added

- README: the integrated subsystems (knowledge layer, Neo4j, 3D explorer, verification, security,
  memory), invariants 8-10, the knowledge graph and memory pages, step 7 (reproduce the trust
  benchmark), a note for a taken Postgres port
- `docs/demo-script.md`: Demo 8 (a planted prompt injection) and Demo 9 (memory), each with a
  fallback that needs no model; a fallback for Demo 7
- `docs/contribution.md`: Members 3 and 4, feature by feature: their original, where it lives now,
  what the port changed, and what was measured
- `teammate-port.md`: the add-ons' as-built status (A1-A15, all built)
- `.claude/README.md`: a reading order for the integration; ADRs 007-011 in the index
- `member-1-scope.md`: what the integration changed about the boundary rule (ported, not imported)

### Fixed

- **The quickstart never said to run the migrations.** On a fresh database the tables did not
  exist, so runs and memory were never stored (contained, logged, invisible). Now step 2
- Stale statements: "CI is red", "eight scenarios", "the API does not persist runs", "no frontend
  test runner", T14's promise of per-case episodic logging (not built, and why)

### Verified

- A clean clone of the committed handover, with a fresh virtualenv and an empty database: every
  quickstart step, a mission and its 3D graph from Neo4j, Demo 8's upload response, the trust
  benchmark reproduced (60/60, 27/27), 925 tests, Vitest and the build

---

## 2026-10-05 - The open bugs: BUG-018, BUG-019, BUG-021 closed

### Fixed

- **BUG-019** (`reasoning/engine.py:unevidenced_values`): when the objective asks for a comparison,
  a fully cited claim stating a date or figure none of its cited lines contains is discarded before
  verification, with a `FINDING_DISCARDED` event naming the values. The negative case no longer
  produces a finding
- **BUG-021** (`trust/specifics.py:numbers_as_dates`): a bare number where a date belongs ("on
  9012") is a `DATE_AMBIGUITY` issue in composite rule 4, and an unevidenced value in the rule above
- **BUG-018**: closed; the specifics check that catches it became the default in Phase 34

### Changed

- `ReasoningEngine.derive_findings(evidence_text=...)`: the controller passes the line text it
  already builds for the verifier

### Measured

- Baseline `20261005T050619`: **every build threshold passes**, the first time since BUG-019.
  `aurora_no_contradiction` 1 finding -> 0; `injection_document` `verification_success`
  1.000 -> 0.667 ("on 9012" caught); nine scenarios unchanged. Aggregate `verification_success`
  0.909 -> 0.970, explained by those two
- 925 tests (5 new)

---

## 2026-10-05 - Phase 34: evaluation and hardening

### Added

- Member 3's seven sample chunks as `.agent/fixtures/documents/shipment_*.txt`, verbatim (K14),
  and `shipment_driver_note.txt`, which carries a planted prompt injection
- Scenarios `shipment_arrival_conflict` (positive, both dates required), `shipment_9012_consistent`
  (negative), `injection_document` (security): the suite is eleven
- Harness: `expect_flagged` and `forbidden_claims`; a missed flag or an obeyed injection fails the
  build; a "Planted injections" report section
- `python -m app.cli eval --out DIR`, so an experiment arm never becomes the baseline;
  `KNOWLEDGE_CROSS_SOURCE_PASS` overrides `agent.yaml` for one process
- `.agent/evals/experiments/`: the three arms of Experiments 003 and 004, with their console output
- Baseline `20261005T042817-qwen3-4b-all`; the first committed trust report
  (`.agent/evals/trust/reports/20261005T044003-lexical`: 60/60, security 27/27)
- `scripts/check_trust_reports.py`: CI re-runs the trust benchmark and the injection suite and
  requires the committed report to match, case by case
- CI: Vitest in the `frontend` job; the memory suite's Neo4j half may not skip
- Invariants: counts for ten vocabularies the port added (`ToolCapability`, `VerificationStatus`,
  `TrustStatus`, `InjectionSeverity`, `EntityType`, `ConflictKind`, `GraphNodeKind`, `GraphLinkKind`,
  `FactKind`, `CrossSourcePass`)

### Changed

- **Default verifier: `composite`** (was `baseline`), by Experiment 004. `.env.example`, `.env`,
  `tools.yaml` and `test_config.py` follow
- The knowledge pass stays `comparative`, now by measurement (Experiment 003)
- `test_no_fixture_document_is_flagged` names the one planted document instead of expecting none

### Fixed

- BUG-022: reports over different sets of scenarios were compared as one; the comparison key now
  includes the scenario ids
- CI's "fail if the database tests skipped" step could never fail: it grepped for skip reasons that
  pytest only prints with `-rs`

### Known Issues

- BUG-019 (open): `aurora_no_contradiction` still produces an invented finding; the composite
  verifier rejects it, and the build still fails on it
- BUG-021 (open): "delivered on 9012" was passed by both verifiers; `injection_document` never
  states the real delivery date
- One run per experiment arm; output varies between model sessions

---

## 2026-10-05 - Phase 33: memory across missions

### Added

- `app/memory/` - Member 4's three tiers (T10-T12), see `.claude/architecture/memory.md`:
  - `distill.py` - pure: the working-memory snapshot, one episode per finding, known entities,
    and facts from claims and relationships **cited by a verified finding** only
  - `episodic.py` - Postgres episodes and archived investigations; `ILIKE` search, newest first
  - `semantic.py` - the `SemanticMemory` protocol and its Postgres store
  - `service.py` - `record_run`, contained; the store chosen by configuration
- `neo4j_store.py:Neo4jSemanticMemory` - `(:KnownEntity)-[:ASSERTS]->(:Fact)-[:ABOUT]->(:KnownEntity)`,
  shared across runs, with uniqueness constraints
- `app/schemas/memory.py` - `WorkingMemorySnapshot`, `Episode`, `ArchivedInvestigation`, `Fact`
  (with `support`, no confidence), `KnownEntity`, `EntityMemory`, and the API views `FactView`,
  `EntityMemoryView`
- Migration `7ae22a602a58`: six `memory_*` tables, each row cascading from its run
- `app/api/v1/memory.py` - `GET /memory`, `/memory/episodes`, `/memory/investigations/{run_id}`,
  `/memory/facts`, `/memory/entities/{name}`; 503 `MEMORY_UNAVAILABLE`, 404 `MEMORY_NOT_FOUND`
- Mission Control: `#/memory` (episode search, entity across missions with facts and support), and
  "seen in N earlier missions" in the graph explorer's pop-up and panel (`recallText`, tested)
- Tests: `test_memory_distill.py` (10), `test_memory_boundary.py` (2), `test_api_memory.py` (9),
  `tests/integration/test_memory.py` (15, both stores), 3 Vitest
- `docs/openapi.json` regenerated: 31 -> 36 paths; `docs/screenshots/phase33-*.png`

### Changed

- Memory is recorded when a mission finishes, after its run row (`registry._run`)
- `tests/conftest.py`: unit tests see no database, so a unit test's mission is never stored in a
  developer's Postgres or memory; only `integration` tests reach it, and they clean up

### Fixed (during the phase)

- `Fact.support_count` was first a `@computed_field`; a fact then failed to re-validate its own
  JSON (schemas.md, decision 5). Now a property, returned through `FactView`; round-trip tested
- `neo4j_store.py` briefly imported two sorting helpers from `app.memory`, a path from run code into
  memory; the helpers moved to `app/schemas/memory.py`, and the boundary test now covers
  `integrations`

### Known Issues

- Facts merge across runs only when the model names the attribute the same way: the same line gave
  `latest_completion_date` in one run and `latest_completion_milestone` in another. Not merged on
  purpose (no synonym guessing); a low support count can mean "phrased differently"
- Memory is written only for missions run through the API (the CLI stores no run rows)
- No API to forget a run's memory yet (the stores support it; tests use it)

---

## 2026-10-04 - Phase 32: the 3D knowledge graph explorer

### Added

- `frontend/src/components/graph3d/` - the knowledge graph explorer (K13, ADR-011):
  - `model.ts` - pure logic: visibility (entities first; claims, documents and citing findings
    unfold under an entity), click highlight to depth 1-3, parents to unfold, filters, search,
    keyboard order, shape/colour/size, `shortLabel`, 2D-or-3D at start
  - `KnowledgeGraph3D.tsx` - the canvas: `3d-force-graph` (three.js) or `force-graph` (2D), one
    instance per mode; nodes restyled in place on highlight; camera framing and fly-to
  - `KnowledgeExplorer.tsx` - controls, hover pop-up, node panel, findings and evidence trail,
    keyboard list, legend; refreshes on `KNOWLEDGE_EXTRACTED`, `FINDING_VERIFIED`,
    `FINDING_REJECTED` and stream close
  - `AnalyzePage.tsx` - `#/knowledge`, analyze documents without a mission
- Routes `#/mission/{id}/graph` and `#/knowledge` (lazy-loaded), a "Knowledge" nav link, and a
  "Knowledge graph" button on the mission page with its conflict count
- API client and types for the Phase 31 knowledge endpoints
- **Vitest**, the frontend's first test runner: `npm test`, 19 tests in `model.test.ts`
- Dependencies: `3d-force-graph` 1.80.1, `force-graph` 1.52.0, `three` 0.186.1,
  `three-spritetext` 1.10.0; dev: `@types/three`, `vitest` 5.0.3
- ADR-011; demo 7 in `docs/demo-script.md`; `docs/screenshots/phase32-*.png`

### Changed

- `vite.config.ts`: `chunkSizeWarningLimit` 1600 kB - the explorer chunk is 1.5 MB (416 kB
  gzipped) and loads only when the view opens; the main bundle is unchanged at 260 kB

### Fixed (during the phase, found by screenshots)

- Graph drawn off-centre (canvas sized to the window until the first resize callback)
- Graph framed tiny, then far too close (`zoomToFit`): the 3D camera is now placed from the node
  positions
- Clicking a node in 3D froze the page under software WebGL: every click rebuilt every mesh and
  label texture; nodes are now restyled in place
- Opening a finding's trail put the camera inside the graph: the fly-to used the origin when the
  target had no position yet

### Known Issues

- The graph is not rebuilt in replay mode (`#/replay`); deferred
- Labels can still overlap where many claims sit close together; the side panel lists them in full
- Verified on Aurora; the shipment scenario in the plan's "done when" arrives with its fixtures in
  Phase 34

---

## 2026-10-04 - Phase 31: the knowledge API

### Added

- `app/api/v1/knowledge.py` - Member 3's 14 endpoints per mission, plus `knowledge` (summary),
  `knowledge/graph`, `knowledge/nodes/{id}`, `findings/{id}/trail`, and `POST knowledge/analyze`
- `app/intelligence/knowledge/view.py` - the graph view (entities, claims as sub-nodes, documents,
  findings; `CONFLICTS_WITH` and `CITES` links), node detail, finding trail; works on either store
- `app/schemas/knowledge.py` - `GraphNode`, `GraphLink`, `KnowledgeGraphView`, `NodeDetail`,
  `FindingTrail`
- `MissionDetail.knowledge_store`, `knowledge_entities`, `knowledge_claims`, `knowledge_conflicts`
  (optional in the frontend types, for old recordings)
- `tests/unit/test_api_knowledge.py` - 22 tests, two against live Neo4j
- `docs/openapi.json` regenerated: 16 -> 31 paths

### Changed

- A mission whose knowledge is in Neo4j is answered after an API restart

### Measured

- 868 tests, all passing with Docker up (none skipped); `mypy --strict` clean (109 modules); 88%
  coverage, 99% on the new route and view modules

---

## 2026-10-04 - Phase 30: the knowledge layer inside a mission

### Added

- `ToolCapability.KNOWLEDGE_GRAPH`; `extract_entities` / `extract_claims` route to it (they used a
  date-and-amount regex)
- `app/tools/knowledge.py` - `knowledge_graph`: conflicts first, each side on its own line naming
  the other with its citation; `mode: conflicts|all`; regex fallback when no knowledge base exists
- The knowledge pass (A5): `agent.yaml:knowledge.cross_source_pass` (`never | comparative | always`)
- `MissionResult.knowledge`, `knowledge_store`, `knowledge_pass_task_id`; `ToolContext.knowledge`
- `KNOWLEDGE_EXTRACTED` (EventType 38 -> 39)
- Neo4j: `(:Finding)-[:CITES]->(:Claim|:Document)` after verification (`record_findings`)
- Evaluation stamp includes the knowledge policy (the BUG-017 rule)
- `tests/conftest.py`: tests never write to a real Neo4j by default
- `tests/unit/test_knowledge_pipeline.py` (13), BUG-020 tests (3), a finding-edge test

### Fixed

- **BUG-020** - for a PDF the reasoning model saw page references and no content.
  `aurora_pdf_timeline` 0 -> 2 findings

### Measured

- New baseline `20261004T172506`: **every positive scenario passes**. The one threshold failure is
  the negative case (BUG-019)
- Knowledge pass off vs on, same session: no positive result changed; +13 s and one task per run.
  The cause is understood: Member 3's rule is same-attribute, and the fixtures' contradictions are
  planned-vs-actual. Experiment 003 (preliminary)
- 846 tests, `mypy --strict` clean (107 modules)

### Known Issues

- BUG-019 still fails CI. The composite verifier's specifics check would catch this session's
  version ("31 January 2026" is not in its cited line), and Exp-004 in Phase 34 decides the default
- Five test runs were written into the local Neo4j by unit tests before `tests/conftest.py`; they
  were removed

---

## 2026-10-03 - Phase 29: Neo4j knowledge graph store

### Added

- `docker-compose.yml` service `neo4j` (5 Community, 512 MB heap, 256 MB page cache, healthcheck)
- `app/integrations/neo4j_store.py` - `Neo4jGraphStore` (one-transaction write per run, load,
  delete) and `Neo4jKnowledgeBase` (the protocol in Cypher plus shared analysis)
- `app/integrations/graph_store.py` - `open_knowledge_base`: Neo4j by default, memory when it is off,
  unreachable or a write fails; probed and logged once per process
- Settings `GRAPH_STORE`, `NEO4J_URI`, `NEO4J_USER`, `NEO4J_PASSWORD`, `NEO4J_DATABASE`; dependency
  `neo4j>=5.20`; healthcheck row `neo4j:connect` (optional)
- `tests/unit/test_knowledge_stores.py` - 34 tests, the protocol suite run against both stores, plus
  Neo4j round trip, run isolation, replace-on-rewrite, conflict edges, and the three fallbacks
- Invariant test: only `neo4j_store.py` imports the driver
- CI integration job: a Neo4j service; the store suite fails the build if it skips
- `ADR-010`

### Changed

- `KnowledgeBase` protocol is async; the investigation aggregate and entity ranking are shared
  functions used by both stores
- The API closes the Neo4j driver on shutdown

### Measured

- Member 3's sample, extracted live and stored in Neo4j: every query answered identically to memory
- 829 tests, `mypy --strict` clean (106 modules)

---

## 2026-10-03 - Phase 28: knowledge core (Member 3's knowledge graph, ported)

### Added

- `app/intelligence/knowledge/` - `extraction.py` (K1, A6-A8), `store.py` (K2-K4), `conflicts.py`
  (K6), `timeline.py` (K7-K8), `graph.py` (K5, no NetworkX), `search.py` (K9), `base.py`
  (`KnowledgeBase` protocol and `InMemoryKnowledgeBase`, K10-K11)
- `.agent/prompts/knowledge.md` v1; `models.yaml` role `knowledge`
- `agent.yaml:knowledge` policy, clamped to new `.env` ceilings `MAX_KNOWLEDGE_CHUNKS` (40) and
  `MAX_KNOWLEDGE_CLAIMS` (2000); both added to the loop-ceiling invariant tests
- `ExtractionStats` gains `claims_capped`, `entities_ungrounded`, `duplicate_claims`
- `tests/unit/test_knowledge.py` - 49 tests
- `.claude/architecture/knowledge-layer.md`; Experiment 005 in the experiment log

### Measured

- Member 3's own sample on `qwen3:4b`, two runs: the planted Shipment 4821 arrival-date conflict
  (14 vs 16 September) found with both citations both times; 40-47 s, 7 calls, 0 failed chunks,
  0 ungrounded claims
- Grounding entity names dropped one mangled name and five names echoed from the known list
- 798 tests, `mypy --strict` clean across 104 modules

### Known Issues

- A value that is on its line but misread passes grounding (Exp 005: "according to security logs"
  read as `received_by`), producing one false conflict per run on the sample
- Not yet used by missions: Phase 30 wires it in. Its settings must join the evaluation stamp then
  (the BUG-017 rule)

---

## 2026-10-03 - Phase 27: security (Member 4's injection guard, ported)

### Added

- `app/security/injection.py` - Member 4's 21 patterns and severity rule, verbatim (tested against
  the archived original), plus 5 `JARVIS_PATTERNS` for measured misses
- Every mission scans every document before the first model call: `INJECTION_DETECTED` (EventType
  37 -> 38), `MissionResult.security`, a report `Limitation`. **A flagged document is still read**
- `POST /api/v1/documents` returns `injection`; `GET /missions/{id}` returns `security_flags`;
  Mission Control shows them (optional field, so pre-Phase-27 recordings still replay)
- `.agent/evals/security/injection_cases.yaml` - 27 cases: Member 4's 14, the 4 adversarial
  strings, 3 attacks on JARVIS's own surfaces, 6 realistic clean texts
- `app/evaluation/security.py`, run by `eval-trust` beside the trust benchmark, as Member 4 ran it
- `.claude/architecture/security.md`
- `tests/unit/test_security.py` - 50 tests, including a full mission over an injected document

### Changed

- Verification prompt v1 -> v2 and reasoning prompt v4 -> v5: document text in escaped
  `<document>` blocks. The wrapper can no longer be closed from inside

### Measured

- Injection suite: Member 4's patterns 22/27, with additions **27/27**, 0 false positives on clean
  cases and on all 14 fixture documents
- Agent suite, `20261003T095400`: no metric moved except latency (26.0 -> 30.3 s). The prompt change
  was A/B tested on the failing negative case, 5 runs each: identical
- 749 tests

### Known Issues

- **BUG-019** - `aurora_no_contradiction` confabulates one finding in the current model session,
  with the same code that passed it earlier the same day. CI's evaluation gate now fails on it as
  well as on `aurora_pdf_timeline`

---

## 2026-10-03 - Phases 25 and 26: groundwork and the trust layer (Members 3 and 4 integration)

Commits `8b04be4`, `ab928d2` (made by the owner, covering Phases 25-26 and early Phase 27 code) and
the Phase 26 close-out commit. Plan: `implementation/integration-plan-phases-25-35.md`. Decision:
ADR-009. Every ported feature: `integrations/teammate-port.md`.

### Added

- `.claude/integrations/originals/` - Members 3 and 4's source, archived verbatim before their
  extracted folders are deleted
- `.claude/integrations/teammate-port.md` - feature inventory K1-K14, T1-T17, original behaviour,
  every deviation and its measured effect
- `ADR-009` - port both teammates in-process rather than call them as services
- `app/intelligence/temporal.py` - one date, time, identifier and figure parser for the knowledge
  layer and the verifier. No invented year; times compared by minute; years in dates are not ids
- `app/schemas/knowledge.py`, `app/schemas/trust.py` - typed contracts for both ports
- `app/intelligence/trust/` - Member 4's verifier: `tfidf.py` (scikit-learn parity, no
  dependency), `lexical.py`, `answer.py`, plus `specifics.py` (A15, not from Member 4)
- `LexicalVerifier`, `CompositeVerifier` - `VERIFICATION_PROVIDER=lexical|composite`
- `VerificationResult.opinions` - every verifier consulted, recorded on the result and the event
- `agent.yaml:verification.lexical` - Member 4's thresholds 0.2 / 0.4 / 0.5
- `python -m app.cli eval-trust` and `app/evaluation/trust.py` - Member 4's benchmark,
  generator byte-identical from seed 42; data in `.agent/evals/trust/`
- Tests: `test_temporal.py`, `test_trust.py`, plus BUG-015 and BUG-016 cases

### Fixed

- **BUG-015** - verification and gap detection read a tool's summary ("11 date(s)") instead of the
  cited line, and PDF page citations resolved to nothing
- **BUG-016** - a locator's detail in the reasoning prompt could come from another document
- **BUG-017** - evaluation reports did not record which verifier ran

### Measured

New baseline `20261003T092851-qwen3-4b-all`, against `20260925T115350`:

| Metric | Before | After |
|---|---|---|
| `verification_success` | 0.750 | 1.000 (audited: see BUG-018) |
| `replanning_success` | 0.787 | 1.000 (vacuous: 0 gaps) |
| `task_efficiency` | 1.756 | 1.447 |
| `latency_s` | 25.8 | 26.0 |
| `aurora_contradiction` | 0 findings, failing | 1 finding, both documents cited, passing |
| `unsupported_claim_rate` | 0.000 | 0.000 |

Trust benchmark: 60/60, hallucination rate 0.000, 1.2 ms per case. 699 tests, `mypy --strict`
clean across 95 modules, 86% coverage.

### Known Issues

- **BUG-018** - the model verifier is lenient on real text. A15 mitigates in `composite`; the
  default stays `baseline` until Exp-004
- `aurora_pdf_timeline` still produces no findings; CI's evaluation gate stays red on it
- Verification model calls do not emit `LLM_CALL_COMPLETED`, so `llm_calls` undercounts
- The repository has mixed line endings (CRLF and LF); a `.gitattributes` normalisation is pending
  the owner's decision
- Phase 27 code (`app/security/`, `INJECTION_DETECTED`, the mission scan) landed in `ab928d2`
  before Phase 27 was tested or documented. It is closed in Phase 27

---

## 2026-09-23 - Phase 6: Intent engine

### Added

- `app/intelligence/intent/engine.py` - `IntentEngine`, the deterministic pre-pass
  (`derive_operations`), operation mapping onto the closed vocabulary, and ambiguity
  detection
- `.agent/prompts/intent.md` - the first prompt asset (version 1)
- `app/cli.py` - `python -m app.cli intent "..."` and `health`; prints the objective,
  the pre-pass, the execution trace and the structured intent
- `backend/tests/unit/test_intent.py` - 24 tests, all on `EchoProvider`
- `docs/demo-script.md`

### Design

- **The model proposes operations as free text; the system maps them.** Constraining the
  model to an enum produces a silent nearest-match; mapping afterwards makes an
  out-of-vocabulary request visible as `UnsupportedOperation` instead of quietly dropped.
- **A deterministic pre-pass runs before the model**, from keywords and file types, so the
  model is never the only signal and the engine degrades to something usable if it fails.
- **Ambiguity is a valid answer.** "Look at these files" yields `clarification_needed`,
  not a confident plan.

### Measured (qwen3:4b, warm)

- Clear objective -> 14 operations, 0 repair attempts, ~3.2 s
- First call after boot ~36 s (one-time VRAM load)

### Changed

- `pyproject.toml` - `app/cli.py` exempted from the `T20` print rule

### Verified

- `pytest -m "not llm"` - 196 passed
- `mypy --strict` - clean, 36 files
- `ruff check` + `format --check` - clean

---

## 2026-09-23 — Phases 4 & 5: LLM abstraction and the event bus

### Added

- `backend/app/llm/` — the only door to a language model (invariant #1)
  - `provider.py` — `LLMProvider` protocol, `CompletionRequest/Response`, `EmbeddingResponse`
  - `ollama.py` — local inference; the only module in the project that speaks HTTP to a model
  - `echo.py` — deterministic fixture provider, plus opt-in JSON-Schema synthesis
  - `structured.py` — `generate_structured()` with the validation-error repair loop
  - `prompts.py` — `PromptLibrary` loading versioned assets from `.agent/prompts/`
  - `telemetry.py` — repair counts, latency and tokens; emits `LLM_CALL_COMPLETED`
  - `errors.py` — typed failures carrying a `FailureClass`
- `backend/app/core/events.py` — `EventBus`, `RunClock`, `RunEventEmitter`, and the
  `Memory`/`Stream`/`TraceFile` sinks
- `backend/app/core/agent_config.py` — the `.agent/config/*.yaml` loader with ceiling clamping
- `backend/app/core/logging.py` — structlog setup, ASCII-only renderer
- Tests: `test_llm.py`, `test_llm_isolation.py`, `test_events.py`, `test_agent_config.py`,
  and `tests/integration/test_ollama_live.py` (marked `llm`, skipped without a model)
- `.claude/architecture/agent-architecture.md`

### Changed

- `models.yaml` gains `think: false`. qwen3 is a reasoning model; see below.

### Findings

- **qwen3:4b is a reasoning model.** Ollama returns its deliberation in a separate
  `thinking` field, and with a modest token budget the deliberation consumes all of it —
  `response` comes back empty with `done_reason=length`. The provider now sends
  `think: false` and reads only `response`, never `thinking`. That field is by definition
  model deliberation, so this is the first line of defence for invariant #3, with event-bus
  redaction as the second.
- **Measured on `qwen3:4b`:** repair rate 0.00 over 3 structured calls, mean latency ~1.6 s.
  A small sample, recorded as a measurement rather than a result. Experiment 001 (Phase 20)
  turns it into a comparison.

### Fixed

- `extract_json` checked `{` before `[`, so a JSON array response silently returned only its
  leading object. Now starts from whichever delimiter appears first.
- `ModelsConfig` rejected the `default: &default` YAML anchor key. Anchors are a
  serialization feature, so the key survives parsing; now accepted and ignored.
- `clamp` and `generate_structured` use PEP 695 type parameters instead of `TypeVar`.

### Verified

- `pytest` — 176 passed, including live-model integration tests against `qwen3:4b`
- `mypy --strict` — clean, 34 source files
- `ruff check` + `format --check` — clean, 44 files
- Isolation tests: no HTTP client outside `app/llm/` and `app/integrations/`; no `os.environ`
  outside `config.py`; no `eval`/`exec`/`compile`/`__import__` anywhere

### Known Issues

- `DatabaseEventSink` is deferred to Phase 3 — a run's timeline currently lives in memory
  and, when `TRACE_TO_FILE=1`, in a trace file.
- Postgres is still the one outstanding Phase 0 criterion, blocked on the WSL2 reboot.

---

## 2026-09-23 — Phase 2: Domain schemas (the typed spine)

### Added

- `backend/app/schemas/` — 12 modules, 97 exported types. Every object crossing a component
  boundary is now a validated Pydantic v2 model (invariant #2).
  - `common.py` — `JarvisModel`/`FrozenModel` bases, `SourceLocator`, `FailureClass` with
    transient/permanent split, typed id helpers, `Money` (exact decimal strings)
  - `objective.py`, `intent.py` — what was asked vs. what was understood, kept separate
  - `tool.py` — `ToolDefinition`, `ToolCall`, `ToolResult`, `ToolSelection`, `SelectionMode`
  - `evidence.py` — `EvidenceRef` vs `Evidence`, `ResolutionStatus`, `EvidenceGap`,
    `ClaimElement`, six `GapType` values
  - `verification.py` — request/result/issue; the request deliberately carries no reasoning trail
  - `finding.py` — `Finding`, `FindingClassification`, and `Confidence`
  - `task.py` — `Task`, 8-state `TaskStatus`, `LEGAL_TRANSITIONS`, `TASK_CAPABILITY`,
    `TASK_SATISFIES`
  - `plan.py` — `Plan`, `PlanValidationResult`, `PlanRevision`, `ViolationCode`, `RepairAction`
  - `event.py` — 38 `EventType` values, `ExecutionEvent`, `ExecutionTrace`, `EventFilter`
  - `execution.py` — `ExecutionState`, `RunStatus`, `RunPhase`, `Observation`, `Budget`,
    `TerminationReason`
  - `result.py` — `FinalReport` with all 11 specified sections, `AgentResult`, `Limitation`
- `backend/tests/unit/test_schemas.py` — 81 tests
- `.claude/api/schemas.md`, `.claude/api/events.md`

### Design decisions

- **`Confidence` has no bare-number constructor.** `Confidence.compute(...)` is the only way
  to make one, and the components travel with the value. "Computed, never asked for" is now
  enforced by the type system rather than by convention.
- **Classification is derived, not declared.** `Finding.classify()` recomputes from evidence;
  validators reject a `FACT` with no resolved evidence and any confidence above its
  classification ceiling.
- **`CONTRADICTED` is distinct from `UNSUPPORTED`.** A contradicted claim is rejected, not
  investigated further — more evidence cannot rescue a claim the sources refute.
- **Closed vocabularies with guards.** Tests assert every `Operation` is satisfiable by some
  `TaskType`, and every `TaskType` maps to a capability.
- **`extra="forbid"` everywhere.** These models parse LLM output; an invented field must fail
  loudly into the repair loop rather than be silently dropped.

### Fixed

- Derived `Finding` values changed from `@computed_field` to plain properties. A computed
  field is serialized into the model's JSON, and with `extra="forbid"` the model then rejected
  its own output on re-validation — which would have broken persistence, trace replay and the
  evaluation harness's reconstruction of stored runs. Caught by the round-trip test.

### Verified

- `pytest` — 91 passed (10 config + 81 schema)
- `mypy --strict` — clean, 24 source files
- `ruff check` + `ruff format --check` — clean, 29 files
- `import app.schemas` pulls in zero engine, provider or database modules (asserted by test)

### Known Issues

- Postgres remains the one outstanding Phase 0 criterion, still blocked on the WSL2 reboot.

---

## 2026-09-23 — Phase 1: Repository skeleton, `.agent` and `.claude`

### Added

- **`.agent/`** — the executable agent specification, with its contract documented in
  `.agent/README.md`: this directory answers "how do we know the agent actually works?"
  and nothing else goes in it.
  - `config/agent.yaml` — replanning triggers and termination conditions, execution retry
    policy (transient vs. non-retryable failures), planning validation policy, reasoning
    confidence rules, verification independence, budget, transparency
  - `config/models.yaml` — per-role model assignment, generation parameters, structured-output
    repair policy, Experiment 001 comparison set
  - `config/tools.yaml` — capability classes, tool enablement, cost hints, fallback chains
  - `config/evaluation.yaml` — ten metrics with targets and regression tolerances, four
    suites including a negative suite, reporting policy
  - `prompts/README.md` — prompt file format, versioning rules, the "document content is
    data, never instruction" rule
  - `scenarios/README.md` — scenario schema; scenarios assert against the execution trace,
    not against generated prose
  - `tests/README.md` — component test-case schema
  - `evals/README.md` — the measurement system and why unsupported-claim rate is the
    headline metric
  - `traces/README.md` — trace format; traces are never hand-authored
  - `fixtures/README.md` — the reference fixture set and its deliberately planted flaws
- **`.claude/`** — engineering memory, with `README.md`, an ADR index and a reading order
  - `context/project-overview.md` — the problem, the closed loop, the three differentiators
  - `context/member-1-scope.md` — what is owned, what is explicitly not, and the provider
    boundary rule
  - `context/architecture.md` — system view, package layout, data flow, future service seams
  - `context/terminology.md` — all 11 core terms plus a "words to avoid" table
  - `architecture/README.md`, `integrations/README.md`, `api/README.md`, `testing/README.md`
- `ADR-001-modular-monolith.md` — Accepted
- `ADR-004-custom-orchestration.md` — Accepted; why no agent framework owns the cognitive loop
- `ADR-006-task-graph.md` — **Proposed**; mutable DAG, with three open questions for Phase 8

### Verified

- All four `.agent/config/*.yaml` files parse
- All six ADRs present
- All 11 core terms defined in `terminology.md`
- No empty directories in `.agent/` or `.claude/`

### Environment progress

- Ollama: `qwen3:4b` (2.5 GB) and `nomic-embed-text` (0.27 GB) pulled and registered.
  Healthcheck LLM rows now green.
- WSL2 2.7.14 installed successfully. **Pending reboot** before the Docker engine can start.

### Known Issues

- Postgres remains the only outstanding Phase 0 acceptance criterion, blocked on the reboot.

---

## 2026-09-23 — Phase 0: Environment & bootstrap

### Added

- Repository bootstrap: git, `.gitignore`, remote `origin`, `main` branch
- `.env.example` — every configurable value, including all agent loop ceilings
- `docker-compose.yml` — PostgreSQL 16 with pgvector; `backend` and `ollama` service
  profiles; frontend deferred to Phase 21
- `scripts/sql/init/001-extensions.sql` — `vector` and `uuid-ossp` on first init
- `backend/pyproject.toml` — dependency set, ruff (with `S` bandit and `BLE` blind-except
  rules), mypy strict, pytest with `integration` and `llm` markers
- `backend/app/core/config.py` — single typed `Settings` object; the only place the
  environment is read
- `backend/Dockerfile`
- `scripts/healthcheck.py` — verifies Postgres, the `vector` extension, and the configured
  LLM provider/model; human-readable and `--json`
- `scripts/dev-up.ps1` / `scripts/dev-up.sh` — one-command bring-up with a health wait
- `backend/tests/unit/test_config.py` — 10 tests, including an assertion that every adaptive
  loop has a positive bounded ceiling (invariant #7)
- `README.md` — quickstart and repository map
- `.claude/context/tech-stack.md`
- `.claude/decisions/ADR-002-postgresql.md`, `ADR-003-ollama.md`, `ADR-005-pgvector.md` —
  all Accepted
- `.claude/logs/development-log.md`, `bug-log.md`, `experiment-log.md`

### Changed

- Config enums use `enum.StrEnum` instead of `(str, Enum)` — the codebase standard going
  forward. The implementation plan's snippets are illustrative on this point.
- Default model set to `qwen3:4b`, chosen against the actual development hardware
  (RTX 4050, ~6 GB VRAM). Configurable, never referenced as a literal outside config.

### Fixed

- BUG-001 — healthcheck crashed with `UnicodeEncodeError` while rendering a FAIL row on the
  cp1252 Windows console. Operator output is now ASCII-only.

### Known Issues

- **Docker engine cannot start:** WSL2 is not installed, and Windows 11 Home has no Hyper-V
  backend. Requires `wsl --install` from an elevated prompt plus a reboot. The Postgres
  acceptance criteria for Phase 0 are outstanding until then.
- **Port 5432 is already bound** by a native PostgreSQL 17 service. Either stop that service
  or set `POSTGRES_PORT=5433` before the first container start.

---

## [0.24.0] — 2026-09-25 — Phases 18-24

The changelog stopped at Phase 0. Rather than reconstruct fifteen releases from memory - which
would be a fabricated history, and the one thing invariant 5 is about - this is one honest entry
covering everything since, with the commit range for anyone who wants the detail.

Commits `1c61c1d`..`491de69`. Per-defect detail in `logs/bug-log.md`; per-session detail in
`logs/development-log.md`.

### Added

- **Report synthesis** (18) - every figure counted from the run; the narrative is the only
  generated text in the document
- **Database persistence** (3) - 11 tables, async SQLAlchemy, batching event sink with a
  terminal-event flush
- **Evaluation harness** (20) - ten metrics computed from real runs, datasets in the repo,
  reports stamped with model + prompt versions + config hash
- **Relevance gate** (13) - a claim that is supported but does not answer the objective is not a
  finding. Fails open; every drop emits `FINDING_DISCARDED` with a reason
- **FastAPI + SSE** (19) - the engine is reachable over HTTP and streams live. Reconnection with
  `Last-Event-ID` replays exactly what was missed: no gap, no duplicate (ADR-008)
- **Headless orchestrator** (19) - `app/orchestration/mission.py`. The CLI, API and UI now render
  one pipeline instead of holding copies of it
- **Mission Control** (21) - React + TypeScript console. Uncertainty is shown, not smoothed, and
  nothing relies on colour alone
- **Trace replay** (22) - a recorded run replays at up to 20x through the same components as a
  live one, and says that it is a replay
- **Evaluation dashboard** (22) - trends that break the series wherever the configuration changed,
  because numbers either side of that are not comparable
- **Invariant and adversarial suites** (23) - the specification's "must not do" list, as tests
  that fail if violated. Injection, malformed plans, corrupt input, zero-finding runs, tool storms
- **GitHub Actions** (23) - lint, types, unit, integration against real Postgres, OpenAPI
  freshness, frontend build, committed-report validation
- **Documentation** (24) - README rewritten, six-demo script, contribution statement, the
  architecture and testing docs the plan named

### Fixed

Eight defects, all found by running the system rather than reading it. BUG-004 to BUG-011.

- **BUG-006** - an input and an output token budget were the same number. Reasoning bounded its
  observations by `max_tokens`, the *generation* limit, so evidence was compressed five times more
  than intended and a scenario with two planted contradictions returned nothing
- **BUG-010** - `RequiredOperation.optional` was defined, filtered on, and never set, so the
  intent demanded 17 operations and no plan could cover them
- **BUG-005** - the agent confabulated 8 findings on a scenario whose correct answer is none
- **BUG-009** - one synonym (`detect_contradictions` vs `detect_inconsistencies`) made an
  objective about contradictions unplannable
- **BUG-004** - a citation parser split on the last colon, so a model quoting the cited line after
  the reference made every finding `UNKNOWN` at zero confidence
- **BUG-011** - `_TOLERANCES` sat below the `__main__` guard, so the regression check never ran
- **BUG-007** - mission list order was unstable when two missions shared a millisecond
- **BUG-008** - a property that changes under the caller made a type checker call live code dead

### Changed

- `plan_validity` **0.667 → 0.333**, and this is honest rather than a behavioural regression. The
  metric counts plans passing with *zero* repairs, and the new terminal-task repair fires on most
  plans. Those plans previously failed outright and produced nothing; the planner needing help is
  now visible instead of fatal
- Plan size cap 20 → 10 once the terminal-task repair made a smaller plan safe to ask for
- Replan insertion capped at 3 tasks per iteration, measured at 24

### Measured

Baseline `20260925T104354-qwen3-4b-all`, against the previous one:

| Metric | Before | Now |
|---|---|---|
| `intent_accuracy` | 0.459 | 0.574 |
| `dependency_correctness` | 0.667 | 0.833 |
| `replanning_success` | 0.411 | 0.658 |
| `task_efficiency` | 3.069 | 2.306 |
| `latency_s` | 91.8 | 45.2 |
| `evidence_coverage` | 1.000 | 1.000 |
| `unsupported_claim_rate` | 0.000 | 0.000 |

581 tests, `mypy --strict` clean across 83 modules, 82% coverage.

### Known Issues

- **The negative scenario confabulates.** 3 findings where none is correct, all restatements of the
  source. CI is red on `main` because of it and the threshold has not been lowered to change that.
  BUG-005, and the highest-value open work
- **The API does not persist runs.** `DatabaseEventSink` exists and is tested; the mission registry
  wires only in-memory sinks, so a restart loses history
- **`app/cli.py` holds a second copy of the pipeline** that should collapse onto the orchestrator
- **Three evaluation scenarios**, where the plan calls for twenty
- **No frontend test runner**, so the replay reconstruction has no unit test
- **CI is red**, correctly: six of seven jobs pass, and `eval-regression` fails on the
  evaluation baseline's positive-case blind spot
- Phase 0's Docker/WSL2 and port-5432 issues are resolved
