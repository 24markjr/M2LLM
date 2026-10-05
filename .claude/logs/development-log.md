# Development Log

Chronological record of implementation sessions. Newest entry at the top of its date.
Every session records: what was implemented, what changed, why, which files, which tests,
and what is still broken.

---

# 2026-10-05 - Phase 34: evaluation and hardening

## What was done

Member 3's sample data became three scenarios (eleven in all), the harness learned to check a
planted injection, the two experiments the plan reserved were run, the defaults were set from them,
and a new baseline was committed. CI now runs Vitest, re-runs the trust and security benchmark, and
its skip checks can fail. The session was paused once (by the owner) after the non-measurement work
and resumed for the runs; arms interrupted by the pause were discarded, not reused.

## The measurements (qwen3:4b, graphs in memory)

| Arm | Knowledge pass | Verifier | Findings that differ | `verification_success` | Mean latency |
|---|---|---|---|---|---|
| A | comparative | baseline | - | 1.000 | 41.5 s |
| B | never | baseline | `shipment_arrival_conflict` 1 -> **0** (blind spot); `helix_evidence_gap` 1 -> 0 | 1.000 | 25.0 s |
| C | comparative | composite | the invented `aurora_no_contradiction` finding **rejected** | 0.909 | 42.0 s |
| Baseline | comparative | composite | = C | 0.909 | 58.7 s |

- **Exp-003:** the knowledge pass finds Member 3's conflict and nothing finds it without the pass.
  Kept.
- **Exp-004:** composite rejected exactly the one fabrication baseline passed, and nothing correct.
  Made the default.
- The baseline repeated arm C finding for finding; its latency was 40% higher with the same work,
  which is the machine (Ollama and other load), not the code. Latency is not compared across runs.

## What the runs exposed

1. **BUG-022.** The first arm printed `REGRESSION CHECK: passed` against the 8-scenario baseline.
   Fixed after the arms (so all arms ran the same code): the comparison key includes the scenarios.
2. **BUG-021.** `injection_document` never stated "20 September". Running it alone printed the
   findings: "delivered ... on 9012", passed by both verifiers, and two findings built on the
   injected note's lines. The security checks pass (flagged, not obeyed); the answer is poor. Open,
   with the fix sketched in the bug log: type a claim's specifics by role.
3. **A CI check that could not fail.** "Fail if the database tests skipped" grepped for skip
   reasons, which pytest prints only with `-rs`. Found while adding the Neo4j memory check beside it.

## Decisions

- **Experiment arms outside `reports/`.** The newest report there is the baseline CI enforces; an
  arm with a non-default setting must never become it. `eval --out` and `.agent/evals/experiments/`.
- **The negative-case rule was not changed** when the composite verifier rejected the invented
  finding and the case still failed. Counting only surviving findings may be right, but changing
  the scoring in the phase whose numbers it would improve is the wrong time to decide it.
- **BUG-021 not fixed here.** A verifier change would have invalidated the experiments that chose
  the defaults; it needs its own measured run.
- **`.env` updated** with `.env.example`: it set `VERIFICATION_PROVIDER=baseline` explicitly, which
  would have overridden the new default on this machine.

## Verification

- `pytest -m "not llm"` -> **920 passed**, none skipped (Docker up); `mypy --strict` clean
  (116 modules); `ruff` and `ruff format --check` clean; 89% coverage; OpenAPI current
- `check_eval_reports.py` fails on BUG-019 only; `check_documented_metrics.py`: 17 figures match;
  `check_trust_reports.py`: current (60/60, 27/27)
- `npm test` -> 22 passed; `npm run build` clean

---

# 2026-10-05 - Phase 33: memory across missions

## What was done

Member 4's working, episodic and semantic memory, fitted to JARVIS: derived from a finished run,
stored in Postgres and Neo4j, searchable through the API and a Memory page, and shown in the graph
explorer as "seen in N earlier missions". Member 4's folder had already been deleted; the port was
made from the line-by-line record in `teammate-port.md` (T10-T12).

## Decisions

- **Facts only from verified findings, episodes from all.** A claim or relationship becomes a fact
  only when a finding that passed verification cites its line; ungrounded claims never do. Every
  finding becomes an episode with its status, rejected ones included.
- **Support, not confidence.** Member 4's `confidence=1.0` is replaced by the (run, line) pairs that
  asserted a fact.
- **The fact store is chosen by configuration, not availability.** With Neo4j configured and down,
  semantic memory is off for that run, rather than written to Postgres where later reads from Neo4j
  would not see it.
- **Working memory is derived** (`distill.working_snapshot`), not a second mutable object; the plan
  named a `working.py`, folded into `distill.py` with the other pure derivations.
- **Unit tests see no database** (`tests/conftest.py`). With Docker up, a unit-test mission would have
  been stored, and its memory shown on the Memory page; the same leak Phase 30 closed for Neo4j.
- **One migration, regenerated** rather than two: `object_key` was added before anything was
  committed, so the first autogenerated revision was downgraded and replaced.

## Checked against real missions (screenshots in `docs/screenshots/`)

Three missions on `qwen3:4b`, Docker up (Postgres, Neo4j):

| Run | Documents | Recorded |
|---|---|---|
| `run_7c9046f1b63c` | project report + financial report | 2 episodes, 8 entities, 3 facts |
| `run_aba9c887510b` | project report + budget CSV | 1 episode, 18 entities, 2 facts |
| `run_1bbb7f668b4a` | repeat of the first | 2 episodes, 8 entities, 3 facts |

- "Project Aurora" is one known entity seen in all three (`phase33-memory-page.png`); its panel in
  the third mission's graph says "seen in 2 earlier missions" (`phase33-graph-recall.png`).
- After the repeat, `PROJECT AURORA approved_budget INR 380,000` had **support 2**: two missions
  citing `aurora_financial_report.txt:r15`. Before it, every fact had support 1.
- **What it exposed:** the same line `r12` gave `latest_completion_date` in one run and
  `latest_completion_milestone` in the other - two facts. Memory does not merge attribute names it
  would have to guess are synonyms. Recorded in `architecture/memory.md` and the changelog.

The plan's "done when" names Rahul Sharma from the shipment fixtures, which arrive in Phase 34. The
same case runs in `test_two_missions_leave_one_known_entity_with_supported_facts`, on both stores.

## What the checks caught

1. `support_count` as a `@computed_field` broke the model's own round trip - the rule in
   `schemas.md` decision 5. Caught while documenting, confirmed by a one-line check, fixed with
   `FactView`.
2. The boundary test, written first, would have passed while `neo4j_store.py` (used during runs)
   imported from `app.memory`; it now covers `integrations`, and the import is gone.
3. The Postgres variants of the store suite skipped silently at first: the availability probe ran
   inside the test's event loop. Fixed by probing once at import; the suite now runs 15 of 15.

## Note on the session

The Vite server from Phase 32 had survived its task being stopped (the `npx` parent ended, the
`node` child did not). Reused for this phase's screenshots, then stopped by its process id.

## Verification

- `pytest -m "not llm"` -> **904 passed** (35 + 1 new); full run with the model: 912
- `mypy --strict` clean (116 modules), `ruff` clean, 89% coverage (memory modules 94-100%)
- `alembic upgrade head`, `downgrade -1`, `upgrade head` clean; OpenAPI current (36 paths)
- `npm test` -> **22 passed**; `tsc -b` clean
- After the tests: no memory rows left in Postgres, no `:KnownEntity`/`:Fact` nodes in Neo4j

---

# 2026-10-04 - Phase 32: the 3D knowledge graph explorer

## What was done

The knowledge graph of a mission as an interactive 3D view (2D fallback), as the owner asked:
entities as nodes with claims and documents as sub-nodes, clicking a node lights up everything
related to it, hovering shows a pop-up, and clicking a finding lights up its evidence trail. Also
Member 3's standalone "analyze documents" page. ADR-011 records the library choice.

## Decisions

- **Vanilla `3d-force-graph` in one wrapper, logic in a pure module.** The plan expected a React 19
  peer conflict with `react-force-graph-3d`; checked, there is none (`react: *`). The reasons that
  stand are in ADR-011: highlight without re-rendering every node through React, and one owner of
  the WebGL lifecycle.
- **Files differ from the plan.** One `model.ts` (pure functions) instead of a `useGraphModel.ts`
  hook, because pure functions test without React; the tooltip, panel and controls stay in
  `KnowledgeExplorer.tsx`, since each is under 60 lines and used once.
- **Entity labels always shown**, not only on highlight as planned. A graph of unlabelled spheres
  told nothing in the first screenshots.
- **No entry animation for new nodes.** Positions of existing nodes are kept across refreshes
  instead, which matters more: a graph that jumps on every SSE event cannot be read.
- **Keyboard users get the side panel, not the pop-up.** It holds the same details and stays put.
- **Replay mode does not rebuild the graph.** A recording holds the `KNOWLEDGE_EXTRACTED` event,
  but not the knowledge base itself. Deferred; noted in the changelog's Known Issues.

## Checked in a browser (screenshots in `docs/screenshots/`)

Headless Chrome with software WebGL, against mission `run_ed5c2de70127` (Aurora, knowledge in
Neo4j: 20 entities, 31 claims, 3 documents, 1 finding). Clicks and hovers were driven through the
Chrome DevTools protocol, not just rendered.

| Check | Result |
|---|---|
| Opens with entities only, framed, labelled | `phase32-3d-overview.png` |
| Click "Project Aurora": its 8 claims, its document, the finding and related entities lit, 13 unrelated nodes faded, panel lists each claim with its line | Pass, 3D and 2D; `phase32-3d-click.png` |
| Hover: pop-up with type, claim count, conflicts, documents | Pass; `phase32-2d-hover.png` |
| Click finding F-001: exactly its trail lit (7 nodes) | Pass; `phase32-3d-trail.png` |
| Reduced motion starts in 2D, same interactions | Pass |

Not checked in the browser: a conflict link (this mission has no conflicts). It is covered by the
unit tests, and the shipment scenario in Phase 34 will have one.

## What the screenshots caught

Each was a real defect, fixed and noted at the constant or function that fixes it:

1. Graph off-centre: the canvas used the window size until the first resize callback.
2. Graph tiny: loose entities repel far apart at the default charge (-30 -> -12).
3. Graph framed far too close by `zoomToFit`: replaced in 3D by our own framing from node positions.
4. **A click froze the page in 3D**: it rebuilt every mesh and label texture. The same click in 2D
   worked, which separated logic from rendering. Nodes are now built once and restyled in place.
5. **The trail put the camera inside the graph**: the finding node was new and had no position, so
   the fly-to moved out from the origin. It now waits for a position and approaches along the
   camera's line of sight.

## Note on the session

A cleanup command (`taskkill /IM chrome.exe` with a window-title filter) stopped every Chrome
process on the machine, not only the headless one. Processes are now stopped by id only.

## Verification

- `npm test` -> **19 passed**; `tsc -b` clean; `npm run build` clean (main 260 kB, explorer chunk
  1.5 MB / 416 kB gzipped, lazy)
- `pytest` -> **876 passed** (868 without the model, plus 8 against the live model); backend
  unchanged this phase

---

# 2026-10-04 - Phase 31: the knowledge API

## What was done

Member 3's REST surface, per mission, with typed errors, and the three views the 3D explorer needs.
The views are built from the `KnowledgeBase` protocol, so they are store-agnostic and tested on
both stores.

## Decisions

- **Running vs finished.** A running mission without a knowledge base yet answers 409 (retry), and
  a finished one 404 (`KNOWLEDGE_NOT_BUILT`), matching how the report route distinguishes "not yet"
  from "not at all".
- **`analyze` stores nothing.** Storing a mission-less knowledge base would recreate Member 3's global
  store.
- **Restart behaviour.** Knowledge in Neo4j survives an API restart and is served. Findings do not
  (they live in the registry), so trails and finding nodes are unavailable then. Stated in the
  endpoint reference rather than hidden.

## Checked

- Seven non-test runs found in Neo4j. Rerunning the knowledge tests left the count unchanged (8
  before, 8 after), so they are not leaks: they are the Phase 30 evaluation missions, stored as
  designed. The clearing query is in `architecture/knowledge-layer.md`.

## Verification

- `pytest tests -m "not llm"` -> **868 passed**, none skipped (Docker up)
- `mypy --strict` clean (109 modules), `ruff` clean, `npm run build` clean, OpenAPI regenerated

---

# 2026-10-03/04 - Phase 30: knowledge in the pipeline

## What was done

The knowledge tool, the re-routing of entity and claim tasks, the knowledge pass, building the
knowledge base before execution, findings as graph edges, and the knowledge policy in the
evaluation stamp. Session interrupted overnight and resumed from the PDF probe.

## The measurement, and what it overturned

The phase was meant to fix the two scenarios keeping CI red, with the knowledge pass as the means.
Measured off vs on in one model session, it fixed neither. Rather than tune it, both failures were
traced:

- `aurora_pdf_timeline` is not a comparison, so the pass never ran there. Printing the reasoning
  prompt showed the cause: for a PDF it carried `aurora_project_report.pdf:p1` and none of the five
  dates on that page (**BUG-020**). Fixed. The scenario passes in both arms.
- On `aurora_contradiction` the knowledge layer paired no conflicts. Its claims showed why: Aurora's
  contradictions are planned vs actual, across two attributes, and Member 3's rule compares one
  attribute. Smaller chunks were tried (300/600/3000 chars) and rejected: slower, more invented
  values, still no pairs.

So the first claim of this phase ("the knowledge pass closes the recall gap") did not survive
measurement, and the gap was closed by a bug fix found while checking it. The pass stays on
`comparative` for the 3D view's sake, with its cost stated, until Experiment 003 on same-attribute
scenarios.

## Also

- Unit tests wrote five runs into the local Neo4j because `GRAPH_STORE` defaults to `neo4j`. Fixed
  with `tests/conftest.py`, and the runs were deleted.
- Docker was down on day two, so the database and Neo4j tests skipped locally (40). They ran green
  in Phase 29 with the services up, and CI runs them with services.

## Verification

- `pytest tests -m "not llm"` -> **846 collected: 806 passed, 40 skipped** (the database and Neo4j
  tests, with Docker down; they passed with services up in Phase 29 and run in CI)
- `mypy --strict` clean (107 modules), `ruff` clean, documented figures checked against the new
  baseline

---

# 2026-10-03 - Phase 29: Neo4j

## What was done

Neo4j 5 Community in compose, an async store behind the `KnowledgeBase` protocol, a factory that
falls back to memory, and one test suite run against both. The protocol became async here rather
than later, because the API (Phase 31) is its first real consumer and the change was cheapest
before anything depended on it.

## Decisions

- **Analysis stays in shared Python.** Re-implementing search scoring or timeline order in Cypher
  would give two answers to one question. Only storage, lookup and the traversal are Cypher.
- **Composite uniqueness, not node keys.** Node keys are Enterprise-only, checked against the
  running container before relying on them.
- **The phase's "done when" was adjusted.** The plan said "a mission writes its graph", but missions
  only build knowledge from Phase 30. The equivalent check was run instead: a live extraction stored
  through the factory and confirmed from Neo4j's side with `cypher-shell`.
- **Run `run_00000000a3a3` is left in the local database** so the graph can be browsed.

## Mistakes caught

- A test assertion built with an escaped newline in a shell heredoc became a real newline and broke
  the file. Repaired. Multi-line edits now go through script files, not heredocs.
- A CI step piped pytest into `tee`, which hides pytest's exit code. Added `set -o pipefail`.

## Verification

- `pytest tests -m "not llm"` -> **829 passed**, with all 17 Neo4j variants run against the live
  container (none skipped)
- `mypy --strict` clean (106 modules), `ruff` clean, healthcheck all green including Neo4j

---

# 2026-10-03 - Phase 28: knowledge core

## What was done

Ported Member 3's extractor, resolver, contradiction detector, timeline, hybrid search and graph
neighbourhood into `app/intelligence/knowledge/`, per run and through `LLMProvider`. The plan's
file split was kept except that `base.py` holds the query protocol, and K5/K10/K11 work in memory
now because search and investigation need them. Phase 29 adds the Neo4j side of the same protocol.

## The acceptance run, and what it changed

Member 3's own sample through the extractor on `qwen3:4b` (Experiment 005) found the planted
arrival-date conflict on the first run, and showed two defects the unit tests had not: an
invented entity name, and duplicate claims. Both were fixed (entity grounding, claim dedup) and the
run repeated. The second run dropped six entity names. Each was checked rather than accepted: five
were names the model echoed from the known-entities list (A8) into chunks that never mention them.
That is a side effect of A8, and grounding is what contains it.

One false conflict per run remains: a misread value that really is on its line. Recorded as the
knowledge layer's measured limit. Its conflicts feed reasoning and are never findings alone.

## Decisions

- Grounding applies to entity names as well as claim values. A name on no line was written, not
  read.
- Relationship endpoints resolve across the run, not the chunk (Member 3 dropped an entity named in
  one paragraph and related in the next).
- Timeline events are grounded claims only. Ungrounded values are kept on the claim list and
  excluded from every analysis.

## Verification

- `pytest tests -m "not llm"` -> **798 passed** (the ceiling checks were added to existing tests)
- `mypy --strict` clean (104 modules), `ruff` clean

---

# 2026-10-03 - Phase 27: security

## What was done

Closed the Phase 27 code that had landed early in `ab928d2`: tests, the case suite, the API and UI
surface, the prompt wrapping, docs. Found two of the four injection strings already in
`test_adversarial.py` undetected by Member 4's patterns, so five patterns were added in a separate
list and every fixture document was checked for false positives (none).

## The measurement that mattered

The post-change evaluation failed a negative case that had passed all day. Rather than revert the
prompt change on suspicion, it was A/B tested: the failing scenario ran 5 times on the code before
Phase 27 (in a git worktree at `83479d3`) and 5 times on the new code. Identical, 5/5 both, and the
Phase 25 commit fails the same way now. The cause is the model session, not the change (BUG-019).
The README's "fixed" claim about confabulation is rewritten.

Lesson: an evaluation run that changes an outcome needs a repeat before it is attributed to the
code. That cost ten minutes here, against reverting a correct security change.

## Verification

- `pytest tests -m "not llm"` -> **749 passed**
- `mypy --strict` clean, `ruff` clean, `npm run build` clean, OpenAPI regenerated
- `eval-trust` -> 60/60 and 27/27; `check_documented_metrics` -> all quoted figures match

---

# 2026-10-03 - Phases 25 and 26: integrating Members 3 and 4

## What was done

**Scanned both teammates' code end to end** (Member 3 `jarvis-member3/`, Member 4
`mem4/MajorP/Mem-4/`), ran their own code from a scratch copy, and recorded the results before
changing anything: Member 4's benchmark 60/60 with scikit-learn and 46/60 without; their verifier
missing every date conflict; their own contradiction demo returning SUPPORTED. Archived both
verbatim and wrote the feature inventory (`integrations/teammate-port.md`), ADR-009 and the
eleven-phase plan. The owner answered D1-D6: Neo4j as default store, both graph uses, keep the
written code, one commit per phase, measure before changing defaults, keep all add-ons.

**Phase 25.** BUG-015 was found by printing what the verifier receives for real tool output.
Fixed with BUG-016 and the shared temporal parser.

**Phase 26.** Ported Member 4's verifier with scikit-learn parity (4.4e-16), the answer
evaluator, the benchmark (byte-identical generator) and two new verification providers. Found
BUG-017 preparing Exp-004.

## Measurements, including the ones that went wrong

- **The first post-fix evaluation ran at 104.7 s per scenario**, `aurora_timeline_only` at 646 s.
  Re-run alone it took 24.6 s, and the full suite re-run gave 26.0 s. The first run overlapped
  Docker Desktop starting and local scratch work; the cause was not proven, and that report was
  discarded rather than committed.
- **`verification_success` 1.000** was audited claim by claim (BUG-018) rather than reported.
  The audit led to A15. A re-run with `composite` did not reproduce the bad claim, because model
  output varies, so A15 is pinned by a unit test and awaits Exp-004.
- `replanning_success` 1.000 is 0 of 0 gaps. It is recorded as vacuous in the README.

## Process notes

- **Git Bash's `grep` hides `\r`**, so early line-ending checks were wrong. `git ls-files --eol`
  is the reliable one. Edits made with `Path.write_text` converted some files to CRLF wholesale.
  Edits now preserve each file's existing ending. The repo was already mixed before this work.
- **The owner commits and pushes between steps.** Phase 27 code started early ended up in
  `ab928d2` with one invariant test failing (EventType 37 -> 38). Fixed forward in the Phase 26
  close-out. **From now on: one phase, fully closed, then stop and report.**

## Verification

- `pytest tests -m "not llm"` -> **699 passed**, 0 skipped (Postgres up: integration tests ran)
- `mypy --strict app` -> clean, 95 files; `ruff check` / `ruff format --check` -> clean
- `check_documented_metrics.py` -> all 16 quoted figures match the new baseline
- `python -m app.cli eval-trust` -> 60/60

---

## 2026-09-23

### 10:45 IST — Phases 4 & 5: LLM abstraction and the event bus

**Order note.** Built Phase 5 before Phase 4, against the plan's numbering. Phase 4's
telemetry emits `LLM_CALL_COMPLETED` through the bus, so building the bus first avoided an
indirection that existed only to preserve a build order. Recorded rather than quietly done.

**Implemented**

- `app/llm/` — provider protocol, Ollama and Echo providers, structured output with repair,
  prompt library, telemetry, typed errors
- `app/core/events.py` — bus, clock, emitter, three sinks
- `app/core/agent_config.py` — YAML loader with ceiling clamping
- `app/core/logging.py`
- 85 new tests across four unit files plus a live-model integration file

**The finding that mattered: qwen3 is a reasoning model**

The live-model acceptance tests failed on first run. Inspecting the raw Ollama response
explained it:

```
response    = ''
thinking    = 'Hmm, the user just asked me to reply with the single word "ready"...'
done_reason = 'length'
```

Ollama puts a reasoning model's deliberation in a separate `thinking` field, and with
`num_predict=64` the deliberation consumed the entire budget before any answer existed.

Two consequences, and the second is the more interesting one:

1. *Practical.* `think: false` now goes on every request, configurable per role in
   `models.yaml`. Without it every evaluation run pays for deliberation tokens it discards,
   roughly doubling latency.
2. *Architectural.* `thinking` is, definitionally, model deliberation — the exact content
   invariant #3 exists to keep out. The provider reads only `response` and never touches
   the field. This is the first line of defence; event-bus redaction is the second. Added
   `test_reasoning_deliberation_never_enters_the_response` to hold it.

This is the kind of thing ADR-003's "build against the harder case" reasoning predicted:
a local model's quirks surface as real engineering rather than being smoothed over by a
forgiving API.

**Measurement on qwen3:4b**

```
repair_rate=0.00  calls=3  mean_latency_ms=1607
```

With `think: false` and JSON mode, the model produced valid structured output first time on
all three calls. Small sample, and deliberately not asserted as a threshold anywhere — the
test prints it rather than checking it, because asserting a number from n=3 would be
inventing a result. Experiment 001 turns this into a real comparison.

**Design decisions**

- **`generate_structured` never guesses.** After exhausting repairs it raises, carrying the
  raw text and the validation errors. A layer that substituted a default would make every
  downstream finding untrustworthy in a way nothing could detect.
- **The repair prompt carries the validation errors verbatim.** Telling the model
  `count: Input should be greater than or equal to 0` fixes far more than asking it to retry,
  and a test asserts the error text actually reaches the second prompt.
- **`EchoProvider` raises by default when no fixture exists.** Synthesis is opt-in. A
  silently synthesized response would let a test pass while proving nothing about the prompt
  it was meant to exercise.
- **Engines take a `RunEventEmitter`, not a bus plus run id plus clock.** Threading three
  things through ten components is how a transition eventually goes unrecorded.
- **`RunClock` uses `perf_counter`.** A wall-clock adjustment mid-run would produce negative
  offsets and an unorderable trace.
- **A lagging SSE subscriber drops events rather than stalling the run.** The client recovers
  its gap by replaying from `Last-Event-ID`; a stalled investigation does not recover.

**Two bugs found by tests**

1. `extract_json` checked `{` before `[`, so a JSON array response silently returned only
   its leading object — a fragment that would have validated as the wrong thing. Now starts
   from whichever delimiter appears first.
2. `ModelsConfig` rejected the `default: &default` anchor key. YAML anchors are a
   serialization feature, so the key survives parsing into the document. Accepted and
   ignored, with a comment explaining why it is there.

**Files**

```
backend/app/llm/{__init__,provider,ollama,echo,structured,prompts,telemetry,errors}.py
backend/app/core/{events,agent_config,logging}.py
backend/tests/unit/{test_llm,test_llm_isolation,test_events,test_agent_config}.py
backend/tests/integration/test_ollama_live.py
.claude/architecture/agent-architecture.md
.agent/config/models.yaml  (think: false)
```

**Tests**

- `pytest` -> 176 passed, including live calls to `qwen3:4b`
- `mypy --strict` -> clean, 34 source files
- `ruff check` + `format --check` -> clean, 44 files
- Isolation suite now enforces: no HTTP client outside `app/llm/` and `app/integrations/`;
  no `os.environ` outside `config.py`; no `eval`/`exec`/`compile`/`__import__` anywhere;
  `app/schemas` imports nothing from the application; `app/llm` never imports engines

**Known issues**

1. `DatabaseEventSink` deferred to Phase 3. Timelines live in memory and optionally in a
   trace file until then.
2. Postgres still blocked on the WSL2 reboot.
3. No prompt assets exist yet — the library is tested against temporary files. Real prompts
   ship with their engines from Phase 6.

---

### 10:15 IST — Phase 2: Domain schemas (the typed spine)

**Implemented**

- 12 schema modules under `backend/app/schemas/`, 97 exported types
- 81 tests in `backend/tests/unit/test_schemas.py`
- `.claude/api/schemas.md` and `.claude/api/events.md`

**The decision that shaped the phase: making invariants unrepresentable**

The instruction was "confidence is computed, never asked for". The weak version of that is a
convention plus a code review habit. The version built instead: `Confidence` has no
constructor taking a bare value. `Confidence.compute(refs=..., classification=...)` is the
only way to produce one, and the inputs are stored alongside the result.

That turned out to be the right pattern for several rules, so it was applied consistently:

| Rule | How it is now enforced |
|---|---|
| Confidence is computed | No bare-number constructor exists |
| A FACT needs resolved evidence | Model validator rejects it |
| A hypothesis cannot look near-certain | Confidence ceiling per classification, validated |
| Verification must be independent | `VerificationRequest` has no reasoning field; a test asserts the field names never appear |
| A rejection must be explainable | `VerificationResult` requires >= 1 issue for any failing status |
| Degradation is never silent | `degraded=True` requires `degraded_reason` |
| A task cannot complete without running | `LEGAL_TRANSITIONS` + `IllegalTransitionError` |
| Reports cannot present unsupported claims as verified | `FinalReport` validator |

The general principle: prefer making an invalid state unconstructable over documenting that
it should not be constructed.

**Bug found by the round-trip test (worth recording)**

`Finding.resolved_evidence_count` and `has_resolved_evidence` were `@computed_field`. A
computed field is serialized into the model's JSON — and with `extra="forbid"`, the model
then **rejected its own output** on re-validation. That would have broken persistence
(Phase 3), trace replay (Phase 22) and the evaluation harness's reconstruction of stored
runs (Phase 20).

Fixed by making them plain properties. The general rule, now documented in the module:
derived values belong in API response models, not in the wire contract of a stored object.
This is exactly what the round-trip test was written to catch, and it caught it on first run.

**Design notes**

- `EvidenceRef` and `Evidence` are deliberately separate types. A ref is what a claim
  *cites*; evidence is what was actually *found*. An unresolvable citation becomes an
  `UNRESOLVED` ref rather than being dropped, which is what feeds gap detection and the
  hallucination metric.
- `CONTRADICTED` vs `UNSUPPORTED` matters more than it first appears: `actionable` is False
  for the former, so the replanning loop will not burn iterations trying to rescue a claim
  the sources refute.
- `TASK_CAPABILITY` and `TASK_SATISFIES` are the bridges between vocabularies. Two tests
  assert the mappings are total, so planning can never emit work that routing cannot serve.

**Files**

```
backend/app/schemas/{__init__,common,objective,intent,tool,evidence,verification,
                     finding,task,plan,event,execution,result}.py
backend/tests/unit/test_schemas.py
.claude/api/{schemas,events}.md
```

**Tests**

- `pytest` -> 91 passed (10 config + 81 schema)
- `mypy --strict app scripts/healthcheck.py` -> clean, 24 source files
- `ruff check` + `ruff format --check` -> clean, 29 files
- Isolation: `import app.schemas` pulls in no engine, provider or database module

**Known issues**

1. Postgres still blocked on the WSL2 reboot. Phase 3 (persistence) needs it; Phases 4-5
   (LLM abstraction, event bus) do not, so the build order can continue either way.
2. `Money` is defined but unused until the CSV/financial tools land in Phase 9.

---

### 09:30 IST — Phase 1: Repository skeleton, `.agent` and `.claude`

**Implemented**

- Full `.agent/` structure with a README per directory documenting that directory's contract
- Four `.agent/config/*.yaml` behaviour-policy files (agent, models, tools, evaluation)
- Full `.claude/` structure: README + ADR index, four context documents, four section READMEs
- `ADR-001` (modular monolith) and `ADR-004` (custom orchestration) — both Accepted
- `ADR-006` (mutable task DAG) — Proposed, with three open questions for Phase 8

**Design decision recorded this session: two configuration surfaces**

`.env` / `Settings` and `.agent/config/*.yaml` could easily have drifted into duplicating
each other. The split, documented in `.agent/README.md`:

- `.env` -> `Settings`: **where things are, and hard safety ceilings** — database URL,
  provider selection, `MAX_REPLAN_ITERATIONS`, `MAX_PARALLEL_TASKS`. Operator-owned,
  per machine.
- `.agent/config/*.yaml`: **how the agent behaves** — model roles, fallback chains, scoring
  weights, evaluation thresholds. Engineer-owned, committed and reviewed.

**The rule that makes the split safe:** YAML can never exceed an `.env` ceiling. Settings
values are hard caps enforced at load time. If `agent.yaml` requests 8 replan iterations and
`MAX_REPLAN_ITERATIONS=3`, the loader clamps to 3 and logs it. Behaviour policy is tunable
from inside the repo; safety bounds are not. The clamping loader is a Phase 4 deliverable —
until it exists, these YAML files are documented but not yet consumed, and that is stated
in each file's header.

**Also recorded:** `.agent/README.md` now carries a phase-to-file map, so it is explicit
which files are deliberately absent rather than accidentally missing.

**Files**

```
.agent/README.md
.agent/config/{agent,models,tools,evaluation}.yaml
.agent/{prompts,scenarios,tests,evals,traces,fixtures}/README.md
.claude/README.md
.claude/context/{project-overview,member-1-scope,architecture,terminology}.md
.claude/{architecture,integrations,api,testing}/README.md
.claude/decisions/{ADR-001-modular-monolith,ADR-004-custom-orchestration,ADR-006-task-graph}.md
```

**Tests / acceptance**

- All four config YAML files parse -> OK
- Six ADRs present -> OK
- 11/11 core terms defined in `terminology.md` -> OK
- No empty directories under `.agent/` or `.claude/` -> OK
- `pytest` 10 passed, `ruff` clean, `mypy --strict` clean (unchanged — Phase 1 adds no code)

**Environment progress since the last entry**

- Ollama models pulled: `qwen3:4b` (2.5 GB) and `nomic-embed-text` (0.27 GB), both
  registered. The healthcheck's two LLM rows are green.
- WSL2 2.7.14 installed via an elevated `wsl --install`. Both optional features enabled;
  DISM reports changes take effect after reboot.

**Known issues**

1. **Reboot pending.** The Docker engine cannot start until Windows restarts. Postgres is
   the only outstanding Phase 0 acceptance criterion.
2. The first `dev-up` after the reboot will start Postgres on **5433** (set in the local
   `.env`) to avoid the pre-existing native PostgreSQL 17 on 5432.

---

### 00:20 IST — Phase 0: Environment & bootstrap

**Implemented**

- Repository bootstrap: `git init`, remote `origin` -> `github.com/24markjr/M2LLM`, branch `main`
- `.gitignore`, `.env.example` (every variable the system reads, including all loop ceilings)
- `docker-compose.yml` — `postgres` (pgvector/pgvector:pg16) by default; `backend` and
  `ollama` behind profiles. Frontend service deferred to Phase 21 so `docker compose config`
  stays valid.
- `scripts/sql/init/001-extensions.sql` — creates `vector` + `uuid-ossp` on first container init
- `backend/pyproject.toml` — dependencies, ruff, mypy strict, pytest config
- `backend/app/core/config.py` — the single `Settings` object (invariant #7)
- `backend/Dockerfile`
- `scripts/healthcheck.py` — verifies Postgres reachability, the `vector` extension, and the
  configured LLM provider + model. Human-readable and `--json` output.
- `scripts/dev-up.ps1` / `scripts/dev-up.sh` — one-command stack bring-up with health wait
- `backend/tests/unit/test_config.py` — 10 tests, including one that asserts every adaptive
  loop has a positive, bounded ceiling
- `README.md` — quickstart

**Changed**

- Config enums use `enum.StrEnum` rather than `(str, Enum)`. Python 3.12 makes the latter a
  lint error (ruff UP042), and `StrEnum` is the same contract. The implementation plan's
  schema snippets show `(str, Enum)` illustratively; the codebase standard is `StrEnum`.
- Added `BLE` (blind-except) to the ruff rule set, so `except Exception` must be deliberate
  and annotated. The healthcheck legitimately needs broad catches — it reports failures, it
  does not raise them.
- Default model set to `qwen3:4b` after checking the hardware (see Decisions below).

**Decisions taken this session**

- **Database:** WSL2 + Docker + `pgvector/pgvector:pg16`, per ADR-002/ADR-005. Chosen by the
  project owner over two alternatives (native PG17 without pgvector; cloud Postgres).
- **Model:** `qwen3:4b` as the development default on an RTX 4050 laptop (~6 GB VRAM). Fits
  fully in VRAM, keeps the evaluation suite cheap enough to run habitually. Phase 20's
  Experiment 001 will compare it against a larger model on identical scenarios.

**Files**

```
.gitignore  .env.example  docker-compose.yml  README.md
backend/pyproject.toml  backend/Dockerfile
backend/app/__init__.py  backend/app/core/config.py  (+ package __init__ files)
backend/tests/unit/test_config.py
scripts/healthcheck.py  scripts/dev-up.ps1  scripts/dev-up.sh
scripts/sql/init/001-extensions.sql
.claude/context/tech-stack.md
.claude/decisions/ADR-002-postgresql.md  ADR-003-ollama.md  ADR-005-pgvector.md
```

**Tests**

- `pytest tests` -> 10 passed
- `ruff check backend scripts` -> clean
- `mypy --strict app scripts/healthcheck.py` -> clean, 12 source files

**Environment findings**

| Component | Status |
|---|---|
| Python 3.12.10 | OK — venv at `.venv`, `pip install -e "backend[dev]"` succeeded |
| Node 24.19.0 | OK — unused until Phase 21 |
| Docker Desktop 29.8.0 | Installed at `%LOCALAPPDATA%\Programs\DockerDesktop`, **engine cannot start** |
| WSL2 | **Not installed.** This is why the Docker engine fails: Windows 11 Home has no Hyper-V backend, so Docker Desktop requires WSL2. Owner action: `wsl --install` in an elevated prompt, then reboot. |
| PostgreSQL 17 | Running natively as service `postgresql-x64-17` on :5432. Not used — the project targets the pgvector container (ADR-002). Note the port conflict when the container starts. |
| Ollama 0.34.2 | Installed via winget, server responding on :11434 |
| GPU | RTX 4050 Laptop (~6 GB VRAM) + Intel UHD; 15.7 GB system RAM |

**Known issues**

1. **Docker engine down pending WSL2 install.** Blocks the Phase 0 Postgres acceptance
   criteria. Everything else in Phase 0 is complete and verified.
2. **Port 5432 is already bound** by the native PostgreSQL 17 service. When the container
   starts, either stop that service or set `POSTGRES_PORT=5433` in `.env`. Decide at the
   first successful `dev-up` run.
3. Healthcheck rendering crashed on the Windows cp1252 console — fixed, see `bug-log.md`.

---

# 2026-09-24 — Phases 19 and 21, and the zero-findings chain

**Commits:** `a59779a`, `cc7a23c`, `8464eed`, `401d0d7`, `2aacaaf`

> **Log coverage note.** This file jumps from Phase 0 to here. Phases 1–18 and 20 were built
> without daily entries; their reasoning lives in the commit messages, the architecture docs and
> `bug-log.md`. That is a real gap in the record and is not backfilled.

## What was built

**Acted on what Phase 20 measured** (`a59779a`). The evaluation harness's first run found three
defects nobody predicted, and fixing them was the point of having built it. The serious one was
confabulation on the negative scenario — see BUG-005. Also capped replan task insertion at 3 per
iteration (one iteration had inserted 24), and planner prompt v2.

Two harness defects surfaced on the way: BUG-011, and reports recording a finding *count* for a
failed negative case rather than the claims — a count says the agent confabulated, not what it
confabulated. Also added the missing mirror check: positive scenarios had **no threshold at all**,
so the relevance gate briefly suppressed every finding on `aurora_contradiction` and the suite
still printed `THRESHOLDS: passed`.

**Phase 19 — FastAPI + SSE** (`cc7a23c`). Built out of order because Phase 21 had no API to call.
Details in `implementation/phase-09-api.md`; the SSE reasoning is ADR-008. The pipeline was
extracted headless into `app/orchestration/mission.py` first, so the CLI, API and UI are renderers
of one run rather than three copies of the sequence.

**Traced the zero-findings chain to its root** (`8464eed`). The Phase 19 smoke run found *no*
findings on the reference scenario with two planted contradictions. Four defects in a chain, each
hiding the next: BUG-006 (token budgets), the terminal-task repair, BUG-009 (one synonym),
BUG-010 (17 required operations).

Measured on the same objective and model:

| | before | after |
|---|---|---|
| tasks planned | 16 | 7 |
| findings | 0 | 4 (3 verified) |
| intent operations | 17 | 7 |

And the behaviour the project exists to demonstrate became visible: a cross-document `INFERENCE`
— *"the budget exceeds the approved amount by INR 70,000"* — citing both reports and surviving
verification. The same run previously returned restatements of a single document.

**Phase 21 — Mission Control** (`401d0d7`). React + TypeScript + Vite, `EventSource` against the
SSE stream so the phase tracker and trace move while the run happens. Uncertainty is shown, not
smoothed, and nothing relies on colour alone. `frontend/README.md` has the detail.

## Verification

- `pytest tests -m "not llm"` -> **529 passed**, 12 skipped (Postgres not running)
- `mypy --strict app` -> clean, **81 source files**
- `ruff check` / `ruff format` -> clean
- `tsc --noEmit` -> clean under `strict` + `noUncheckedIndexedAccess` +
  `exactOptionalPropertyTypes`
- `npm run build` -> 243 kB (76 kB gzipped)
- Live Aurora run over **real uvicorn**, not only the ASGI test transport: 82 events streamed,
  reconnect from event 3 delivered exactly the 79 that followed

## Decisions taken

**Phase 19 before Phase 21.** Phase 21's acceptance criterion is that the UI starts a real run.
A frontend against a non-existent API is a mock, and a mock is what fails in front of an
evaluator who clicks something.

**Plan cap left at 20, then lowered to 10 once the blocker was fixed.** Lowering it alone made
things worse — the model dropped its terminal task and every plan failed validation, so the run
produced nothing instead of a smaller plan. The deterministic terminal-task repair had to come
first. Recorded in `agent.yaml` at the setting, including the failed attempt.

**Frontend dependencies are React and nothing else.** The plan named Tailwind, React Query,
Zustand, Recharts and Framer Motion. Hand-written CSS, `fetch`, `useState` and `EventSource`
cover what this console does, and each library omitted is a toolchain that cannot break during a
demo. Deviation and what to add first are recorded in `frontend/README.md`.

## Known issues

1. **The evaluation suite has not been re-run** since the intent, plan-cap and observation-budget
   fixes. The committed baseline predates them, so its numbers are stale and the regression check
   will correctly refuse to compare (prompt versions changed). **This is the cheapest next
   action.**
2. **The CLI still holds its own copy of the pipeline.** The orchestrator exists and the API uses
   it; collapsing `run_investigate` onto it was deferred to avoid destabilising the demo path.
   Duplication that will drift.
3. **API runs are not persisted.** `DatabaseEventSink` exists but the registry wires only
   in-memory sinks, so a restart loses history.
4. **The timeline contradiction surfaces less reliably than the budget one**, and the model
   attaches a currency (`INR`) the documents do not state.
5. **One restatement still leaks** on the negative case intermittently. The suite fails the build
   on it rather than tolerating it.
6. **Three evaluation scenarios, not the twenty the plan calls for.**
