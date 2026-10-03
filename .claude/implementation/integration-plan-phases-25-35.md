# JARVIS — Integration Plan: Members 3 and 4 (Phases 25–35)

**Status:** Approved 2026-10-03, decisions D1-D6 recorded in §3
**Written:** 2026-10-03
**Continues:** [`implementation-plan.md`](implementation-plan.md), Phases 0–24
**Source being integrated:** Member 3 (`jarvis-member3/`) and Member 4 (`mem4/MajorP/Mem-4/`).
Every feature is inventoried with its original behaviour in
[`../integrations/teammate-port.md`](../integrations/teammate-port.md) (K1–K14, T1–T17) and
archived verbatim in [`../integrations/originals/`](../integrations/originals/).
**Decision record:** [ADR-009](../decisions/ADR-009-port-teammates-in-process.md), port in-process.
This plan adds **ADR-010** (Neo4j) and **ADR-011** (3D graph explorer).

---

## 0. How to read this

Eleven phases, each with the same sections: **Goal**, **Ports** (which teammate features),
**Build** (the work, file by file), **Design** (the decisions that are not obvious), **Tests**,
**Done when** (acceptance criteria), and **Documents** (what gets written).

The invariants from Phases 0–24 apply to every phase here without exception. They are tested,
so a phase that breaks one fails CI:

1. The model is reached only through `app/llm/`.
2. Every boundary is typed. No dicts cross a component boundary.
3. No model deliberation is persisted.
4. A run is reconstructable from its events. Nothing from another run leaks into it.
5. No fabricated behaviour. No hand-written metric, trace or report.
6. Closed vocabularies. New event types, capabilities and statuses are deliberate and counted.
7. Every loop is bounded and every ceiling is configured.

Two rules this plan adds, both following from the teammates' code:

8. **Knowledge is scoped to a run.** Every node, edge and claim carries the `run_id` that built
   it. Cross-run knowledge exists only in memory (Phase 33), is opt-in, and is never read back
   into a run by default.
9. **Optional infrastructure degrades, it never blocks.** Neo4j, like Postgres, is optional.
   `python -m app.cli investigate` must keep working with only Ollama running.

### Requested by the user (2026-10-03)

| Request | Where |
|---|---|
| Re-implement every Member 3 and Member 4 feature, same logic, in this codebase's style | Phases 26–33 |
| Use **Neo4j** for the knowledge graph | Phase 29, ADR-010 |
| Knowledge graph **interactive and 3D** | Phase 32, ADR-011 |
| Nodes with **sub-nodes**; **clicking a node highlights all its related sub-nodes** | Phase 32 §Interactions |
| **Hovering a node shows a pop-up** with that node's information | Phase 32 §Interactions |
| Document every single thing | Every phase has a **Documents** section; §5 lists the logs |

### Add-ons proposed in this plan (not requested; each can be dropped)

| # | Add-on | Why | Phase |
|---|---|---|---|
| A1 | **BUG-015 fix**: the verifier reads the cited line, not a tool summary | Found during the scan: verification compared claims against `"11 date(s)"`. Member 4's verifier cannot work without it | 25 |
| A2 | **BUG-016 fix**: observation details match on document *and* line | Two documents with an item on the same line number get their details mixed. The knowledge tool emits exactly that | 25 |
| A3 | **Composite verifier**: LLM baseline plus lexical, with a contradiction veto | Lexical is precise on numbers and dates, the LLM on meaning. Neither alone is enough | 26 |
| A4 | **Date conflicts** in the lexical verifier | The original only caught clock times; a wrong date was never `CONTRADICTED` | 26 |
| A5 | **Knowledge pass for comparative objectives** | Targets the open recall defect (BUG-005/012): `qwen3:4b` will not pair claims across documents, so the knowledge layer pairs them deterministically | 30 |
| A6 | **Claim grounding**: every extracted value checked against its source line | A value the model wrote rather than read is flagged and never used to detect a conflict | 28 |
| A7 | **Deterministic CSV extraction** | Row-level claims with exact locators and no LLM call | 28 |
| A8 | **Shared attribute vocabulary across chunks** | The original's biggest recall limit: "arrival_date" vs "arrived_on" never matched | 28 |
| A9 | **Evidence trail in 3D**: click a finding to light up the subgraph it rests on | Turns "every claim is bound to evidence" from a sentence into something visible | 32 |
| A10 | **Live graph growth** during a mission, over the existing SSE stream | The 3D view builds while the agent works, rather than appearing at the end | 32 |
| A11 | **Injection scan at document load**, with an event and a report limitation | Member 4's scanner existed but nothing called it | 27 |
| A12 | **Trust and security benchmarks inside the evaluation harness**, stamped like the agent reports | Their benchmark becomes a regression gate instead of a script | 26, 27, 34 |
| A13 | **Three new mission scenarios** from Member 3's shipment sample, including a negative case and an injection case | The current suite has never seen this domain | 34 |
| A14 | **Cross-investigation graph** in Neo4j memory: the same entity across past runs | The one thing Neo4j does that the per-run graph cannot | 33 |

---

## 1. Phase map

```
25 Groundwork ──┬── 26 Trust layer ───── 27 Security
                │
                └── 28 Knowledge core ── 29 Neo4j store ── 30 Pipeline wiring ── 31 Knowledge API ── 32 3D explorer
                                                                                       │
                                                         33 Memory ─────────────────────┘
                                                                │
                                              34 Evaluation & hardening ── 35 Documentation & handover
```

| # | Phase | Ports | Size | Depends on |
|---|---|---|---|---|
| 25 | Groundwork: bug fixes, shared temporal parser | — | S | — |
| 26 | Trust layer: lexical and composite verification, trust benchmark | T1–T6, T13–T16 | M | 25 |
| 27 | Security: injection scanning and safe prompts | T7–T9 | S | 25 |
| 28 | Knowledge core: extraction, resolution, conflicts, timeline, search | K1–K4, K6–K9 | L | 25 |
| 29 | Neo4j graph store | K5, K10, K11 | L | 28 |
| 30 | Knowledge in the mission pipeline | — | M | 29 |
| 31 | Knowledge API | K12 | M | 30 |
| 32 | 3D knowledge graph explorer | K13 | L | 31 |
| 33 | Memory: working, episodic, semantic | T10–T12 | M | 29, 31 |
| 34 | Evaluation and hardening | K14 | M | 26–33 |
| 35 | Documentation and handover | — | S | 34 |

**Minimum viable integration**, if time runs short: 25, 26, 28, 30, 34. That delivers verified
cross-document contradictions in the agent's own findings, which is what the open defect needs.
Neo4j and the 3D view (29, 31, 32) are what makes it demonstrable.

---

## 2. The phases

### Phase 25 — Groundwork

**Goal:** fix the two defects that would make every later phase measure the wrong thing, and build
the one parser both teammates needed.

**Ports:** none directly; prepares T3/T4 and K6/K7.

**Build**

| File | Change |
|---|---|
| `app/intelligence/replanning/controller.py` | **BUG-015.** `evidence_from_observations(observations, documents, page_starts)` reads the text at each locator: a line for `:rN`; for `:pN`, the lines a tool matched on that page, else the page capped at 1,200 characters. Page locators stay pages. The controller passes the run's documents. *Already written, uncommitted.* |
| `app/intelligence/reasoning/engine.py` | **BUG-016.** `_detail_for` matches `document_id` as well as `line`. |
| `app/intelligence/temporal.py` | Shared date, time, identifier and number parsing (§Design). *Already written, uncommitted.* |
| `app/schemas/knowledge.py` | `PartialDate`, `ClaimOrder`, `TimelineRelation`, needed by the parser. *Already written, uncommitted.* |

**Design**

- **Dates never get an invented year.** `PartialDate(year?, month, day?)`. Two dates are
  *compatible* if every field known on both sides agrees. Member 3 forced every date to 2026,
  including dates that stated their own year.
- **Times compare by the minute they denote.** `11:40` is compatible with `11:40 AM`. Member 4
  compared strings, so those two were a conflict.
- **A year inside a date is not an identifier.** Member 4's `\b\d{3,}\b` read "2026" as a shared
  shipment id.
- **Numbers parse only when the value is one number.** `INR 380,000` → 380000; `Phase 2 of 3` →
  none.

**Tests:** `test_replanning.py` (4 added: real tool output, page locator, page cap, unreadable
locator); `test_temporal.py` (every original format, abbreviations, invalid dates such as
31 February, times with and without am/pm, identifiers with dates masked, numbers);
`test_reasoning.py` (two documents, same line number, details not mixed).

**Done when:** a verifier given a citation of `aurora_project_report.txt:r10` receives
"The approved baseline completion date is 30 April 2026." (measured on the probe that found
BUG-015); the full suite, mypy and ruff are clean; **the evaluation suite is re-run** and its
baseline replaced. BUG-015 changes what verification sees, so every earlier number is from a
different system.

**Documents:** bug-log BUG-015 and BUG-016 (cause, why the tests missed it, fix, measured
effect); changelog; development log.

---

### Phase 26 — Trust layer

**Goal:** Member 4's verifier and hallucination evaluator working inside JARVIS's verification
seam, and their benchmark as a measured gate.

**Ports:** T1 TF-IDF, T2 overlap fallback, T3 verifier, T4 conflict rule, T5 answer evaluator,
T6 contradiction demo, T13–T15 benchmark, T16 schemas.

**Build**

| File | Content |
|---|---|
| `app/schemas/trust.py` | `TrustStatus` (their five statuses, unchanged), `EvidenceText`, `ScoredEvidence`, `LexicalThresholds`, `LexicalVerdict`, `AnswerAssessment`, `InjectionScan`. *Written.* |
| `app/intelligence/trust/tfidf.py` | TF-IDF identical to `TfidfVectorizer(stop_words="english")` with no scikit-learn dependency. *Written; parity with scikit-learn 1.9.1 measured at 4.4e-16.* |
| `app/intelligence/trust/lexical.py` | `verify_claim`, the original procedure step for step, with A4. *Written; 60/60 on their benchmark.* |
| `app/intelligence/trust/answer.py` | `evaluate_answer`, unchanged logic. *Written.* |
| `app/integrations/verification.py` | `LexicalVerifier` and `CompositeVerifier`, both `VerificationProvider`s |
| `app/core/config.py` | `VerificationProviderName` gains `LEXICAL`, `COMPOSITE` |
| `.agent/config/agent.yaml` | `verification.lexical: {relevance: 0.2, support: 0.4, conflict: 0.5}` |
| `app/evaluation/trust.py` | Benchmark generator (seed 42, identical output to theirs) and runner |
| `.agent/evals/trust/` | `benchmark.json`, `evidence_corpus.json` (their data, verbatim), and reports |
| `app/cli.py` | `python -m app.cli eval-trust` |

**Design**

*Status mapping*, the only place the two vocabularies meet:

| Member 4 | JARVIS `VerificationStatus` | Issue attached |
|---|---|---|
| `SUPPORTED` | `SUPPORTED` | — |
| `CONTRADICTED` | `CONTRADICTED` | `SOURCE_CONFLICT`, naming the conflicting locator and the reason ("dates 2026-09-20 vs 2026-09-14 on shared id 4821") |
| `UNSUPPORTED` | `UNSUPPORTED` | `EVIDENCE_MISMATCH` |
| `INSUFFICIENT_EVIDENCE` | `INCONCLUSIVE` | `NO_EVIDENCE`. Never a pass |

*`CompositeVerifier`* (A3) runs both and resolves:

1. Lexical says `CONTRADICTED` and the LLM does not → **`CONTRADICTED`**. The rule needs a shared
   identifier, disjoint dates or times, and relevance ≥ 0.5. That is high precision.
2. The LLM is `INCONCLUSIVE` (it failed to produce a verdict) and lexical is decisive → lexical's
   verdict, with `degraded=True` and the reason. Never silent (invariant 5).
3. Otherwise → the LLM's verdict. A lexical `SUPPORTED` never overrides an LLM rejection,
   because word overlap is not meaning.
4. Every disagreement is in the `FINDING_VERIFIED`/`FINDING_REJECTED` payload
   (`"lexical": "<status>"`), so how often they disagree can be measured.

*Default provider:* stays `baseline` until Phase 34 measures `composite` on the full suite. The
default changes only if `unsupported_claim_rate` does not rise and `verification_success` does
not fall outside its tolerance.

*Confidence:* the lexical relevance score is **not** used as confidence. It is not calibrated,
and "confidence is computed, never asserted" applies. The verdict confidence uses the
baseline's existing derivation from the number of distinct documents.

**Tests:** `test_trust.py`. TF-IDF parity on fixed vectors. Each decision branch. The four
shipment probes from the scan, which now give `SUPPORTED`, `CONTRADICTED`, `SUPPORTED`,
`UNSUPPORTED`. The contradiction demo (T6) as a test. Answer evaluation on a mixed answer giving
`PARTIALLY_SUPPORTED`. Every status mapping. Composite resolution rules 1–4. No path where
`INSUFFICIENT_EVIDENCE` becomes `SUPPORTED`.

**Done when:** `eval-trust` reproduces 60/60 on their benchmark, with hallucination rate 0.0 and a
report stamped with config hash and thresholds; the four shipment probes match the table above;
selecting `VERIFICATION_PROVIDER=composite` runs a full mission.

**Documents:** `teammate-port.md` T1–T6 and T13–T16 marked `DONE`/`CHANGED` with each deviation's
measured effect; `.claude/architecture/verification.md` gains a "lexical and composite" section;
`.claude/testing/agent-evaluation.md` documents the trust benchmark; changelog.

---

### Phase 27 — Security

**Goal:** Member 4's injection scanner running on every document JARVIS reads, visibly.

**Ports:** T7 scanner, T8 safe prompt construction, T9 adversarial suite.

**Build**

| File | Content |
|---|---|
| `app/security/injection.py` | The five categories and their patterns verbatim; the severity rule verbatim; `wrap_untrusted`, `build_safe_prompt` |
| `app/schemas/event.py` | `INJECTION_DETECTED` (EventType 37 → 38) |
| `app/orchestration/mission.py` | Scan every document before planning; emit per flagged document; record on `MissionResult.security` |
| `app/intelligence/synthesis/engine.py` | A flagged document becomes a report `Limitation`: "aurora_x.txt contains text resembling a prompt injection (HIGH: system_prompt_extraction); treated as data" |
| `app/api/v1/documents.py` | The upload response includes the scan, so a user sees the flag before starting a mission |
| `.agent/evals/security/injection_cases.yaml` | Their 14 cases, plus cases against JARVIS's own surfaces: a fake locator, a fake JSON finding, and `</document>` used to break out of a wrapper |
| `.agent/prompts/{reasoning,verification,knowledge}.md` | Document text wrapped in `<document source="...">` blocks; version bumped |

**Design**

- **Flag, never drop.** A security report that quotes an attack phrase matches the patterns. If
  the document were dropped on a match, an attacker could delete evidence by quoting a phrase.
  The content is still read, as data. Both the report and the event say so.
- **Wrappers cannot be closed from inside.** The original's `wrap_untrusted` would let a
  document containing `</document>` end the block early. The port escapes it. This is a
  deviation with a test.
- **The prompt change is measured.** Wrapping changes three prompts, so their versions bump and
  Phase 34's evaluation run is what shows the effect. It is not assumed.

**Tests:** `test_security.py` (each category, each severity, the escape, 14/14 on the original
suite, plus the new cases); `test_adversarial.py` extended with a mission over an injected
document that completes and reports the flag; the vocabulary-size invariant updated to 38.

**Done when:** the suite detects all attacks with 0 false positives on the clean cases; an
injected document raises `INJECTION_DETECTED`, appears in the report's limitations, and does not
change the plan.

**Documents:** `teammate-port.md` T7–T9; `.claude/api/events.md` (`INJECTION_DETECTED`);
`.claude/architecture/` security note; changelog.

---

### Phase 28 — Knowledge core

**Goal:** Member 3's knowledge layer as a typed, per-run engine, reached through `LLMProvider`.
Storage is in memory here; Phase 29 adds Neo4j behind the same interface.

**Ports:** K1 extraction, K2 resolution, K3 relationships, K4 claims, K6 contradictions,
K7–K8 timeline, K9 search.

**Build**, all under `app/intelligence/knowledge/`:

| File | Content |
|---|---|
| `extraction.py` | `KnowledgeExtractor`: chunking, LLM calls through `generate_structured`, grounding (A6), CSV path (A7), attribute vocabulary (A8) |
| `store.py` | `KnowledgeStore` protocol and `InMemoryKnowledgeStore`: entities, relationships, claims, resolution |
| `conflicts.py` | K6 |
| `timeline.py` | K7, K8 |
| `search.py` | K9 |
| `base.py` | `KnowledgeBase`: one query surface over a store. `entities`, `find_entity`, `relationships`, `claims`, `conflicts`, `timeline`, `compare`, `network`, `evidence`, `investigate`, `search` |
| `.agent/prompts/knowledge.md` | v1. Same three outputs as Member 3's prompt, plus a line number per item |
| `.agent/config/models.yaml` | role `knowledge` (max_tokens 1,500) |
| `.agent/config/agent.yaml` | `knowledge: {enabled, chunk_chars: 3000, max_chunks: 12, max_claims: 400, cross_source_pass: comparative}`, every ceiling clamped |

**Design**

*Extraction (K1)*
- Each chunk is sent with numbered lines (`12| The approved baseline ...`), and the model returns
  a line number with every claim and relationship. The model is reached through `LLMProvider`
  with schema-constrained decoding. The original used `requests` to a hard-coded model.
- **Grounding (A6).** A claim's value must appear on its stated line: case- and
  space-insensitive, or as an equal date, or as an equal number. If it doesn't, the extractor
  searches the chunk's other lines. If the value is found nowhere, `grounded=False`. The claim is
  kept and shown, and **never used to detect a conflict**. Counted in `ExtractionStats`.
- **Attribute vocabulary (A8).** Attribute names already used in this run are passed into the
  next chunk's prompt ("reuse these when they fit"), along with known entity names. This
  addresses the original's main limit, where the same fact under two attribute names never
  conflicts.
- **CSV (A7).** No LLM. The first mostly-non-numeric column is the entity, each other column an
  attribute, each cell a claim at its exact row.
- **Bounded (invariant 7).** Chunks beyond `max_chunks` are not sent and are counted as
  `chunks_skipped`. A knowledge base built from half the documents can never look complete.

*Resolution (K2–K4).* Same rule as the original, a normalised name, slightly widened: casefold,
collapse whitespace, strip punctuation such as `#`, and drop a leading "the". Aliases are
recorded. **Fix:** a claim about an unextracted entity creates that entity (type `OTHER`)
instead of being stored under its raw name. Relationships with unknown endpoints are skipped, as
in the original, and counted. IDs are sequential per run (`ENT-001`), not random, so a run is
reproducible.

*Contradictions (K6).* Same grouping, (entity, attribute) with more than one distinct value,
and still never picks a winner. Values compare by kind: dates as compatible `PartialDate`s,
numbers as numbers (`INR 380,000` = `380000`), otherwise casefolded text. Only grounded claims
take part.

*Timeline (K7–K8).* Original labels and ordering. A claim enters if its attribute contains
"date" or "time" (the original rule) **or** its value parses as a date (an addition, recorded).
No invented year. For ordering only, a missing year is inferred from the most common explicit
year in the run, with `year_inferred=True` on the event.

*Search (K9).* The original's +3 / +1 / +n / +1 score, with every point's reason. **Fix:** the
"has a source" point is added only to a claim that already matched something. Otherwise every
claim scores at least 1 and search returns everything, which is what the original did.

**Tests:** `test_knowledge.py`, all on `EchoProvider` with queued responses. Extraction shape,
line grounding, ungrounded flagging, CSV rows, chunk ceiling. Resolution: aliases, case,
punctuation, unknown-entity claims, skipped relationships. Conflicts by date, number and text,
ungrounded excluded. Timeline: order, labels, no invented year. Compare: all four results.
Search: the original's scores on the original sample, and the always-returns-everything fix.
Run isolation: two knowledge bases in one process share nothing.

**Done when:** Member 3's `sample_data.json`, run through the extractor with `qwen3:4b`, yields
the Shipment 4821 `arrival_date` conflict (14 vs 16 September) with both sources, and an
investigation of "Shipment 4821" returns its documents, network, claims and conflict. Recorded
in the experiment log with the real output.

**Documents:** `teammate-port.md` K1–K4 and K6–K9; new
`.claude/architecture/knowledge-layer.md` (data model, extraction, grounding, resolution, the
deviations and why); changelog.

---

### Phase 29 — Neo4j graph store

**Goal:** the knowledge graph stored in and queried from Neo4j, with the in-memory store as the
fallback when Neo4j is not running.

**Ports:** K5 graph and neighbourhood, K10 investigation, K11 evidence lookup, plus the
storage half of K2–K4.

**Build**

| File | Content |
|---|---|
| `docker-compose.yml` | `neo4j:5-community` service: ports 7474 (browser) and 7687 (Bolt), a named volume, heap and page-cache limits sized for a laptop (512 MB / 256 MB), a healthcheck, `NEO4J_AUTH` from `.env` |
| `.env.example`, `app/core/config.py` | `GRAPH_STORE=memory\|neo4j`, `NEO4J_URI`, `NEO4J_USER`, `NEO4J_PASSWORD`, `NEO4J_DATABASE` |
| `backend/pyproject.toml` | `neo4j>=5.20` (the official async driver) |
| `app/integrations/neo4j_store.py` | `Neo4jKnowledgeStore` implementing the Phase 28 protocol. Lives in `integrations/`, the one package allowed to talk to an external service |
| `app/integrations/graph_schema.cypher` | Constraints and indexes, applied idempotently at startup |
| `scripts/healthcheck.py` | A Neo4j row, like the Postgres one |
| `.github/workflows/ci.yml` | `integration` job gains a Neo4j service container |

**Design**

*Graph model*

```
(:Run {run_id, objective, created_at})
(:Document {run_id, document_id, kind})
(:Entity {run_id, entity_id, name, type, aliases})
(:Claim {run_id, claim_id, attribute, value, source, line, page, grounded, quote})
(:Finding {run_id, finding_id, claim, status})                       ← Phase 30

(:Run)-[:HAS_DOCUMENT]->(:Document)
(:Entity)-[:MENTIONED_IN {source}]->(:Document)
(:Entity)-[:RELATES {predicate, source}]->(:Entity)
(:Entity)-[:HAS_CLAIM]->(:Claim)
(:Claim)-[:CITED_IN {source}]->(:Document)
(:Claim)-[:CONFLICTS_WITH {conflict_id, attribute, kind}]->(:Claim)
(:Finding)-[:CITES]->(:Claim | :Document)                            ← Phase 30
```

Constraints: unique `(run_id, entity_id)`, `(run_id, claim_id)`, `(run_id, document_id)`; an index
on `Entity.name`. **Every query filters on `run_id`** (rule 8). A test reads one run's graph while
another run's graph is in the database and asserts nothing crosses over.

*Why Neo4j earns its place here* (recorded in ADR-010): the neighbourhood query (K5), the
investigation aggregate (K10) and the cross-run memory graph (A14) are path queries. The
original rebuilt a NetworkX graph from SQLite on **every** request; Neo4j answers
`MATCH (e:Entity {run_id:$r, entity_id:$id})-[*1..$depth]-(n)` from an index.

*Why it stays optional:* the demo machine runs Windows 11 Home, where Docker needs WSL2 and has
been down for most of this project. `GRAPH_STORE=memory` gives identical behaviour without it.
Availability is probed once per process, as Postgres is. If Neo4j is unreachable, the run uses
memory and logs one `graph_store_degraded` line. **A Neo4j failure never fails a run.**

*Writes* are batched per run with `UNWIND`, one transaction at the end of extraction, so a run
never sees a half-written graph.

**Tests:** the protocol suite from Phase 28 runs **against both stores** (parametrised), so
memory and Neo4j are held to identical behaviour. Integration tests are marked `requires_neo4j`
and skip when it is not running, which is the existing Postgres pattern. Run isolation is tested
on Neo4j. The degradation path is tested with an unreachable URI.

**Done when:** `docker compose up -d neo4j` plus `GRAPH_STORE=neo4j` makes a mission write its
graph, and it is visible in the Neo4j browser at <http://localhost:7474>; the parametrised suite
passes on both stores; with Neo4j stopped, the same mission completes on memory with one
degradation log line.

**Documents:** **ADR-010** (Neo4j, why and why optional); `.claude/architecture/knowledge-layer.md`
gains the graph model; `tech-stack.md`; the README quickstart (an optional step); changelog.

---

### Phase 30 — Knowledge in the mission pipeline

**Goal:** the agent uses the knowledge layer during a mission, and its conflicts reach the
reasoning engine as pairs it can cite. This is the phase aimed at the open recall defect.

**Build**

| File | Change |
|---|---|
| `app/schemas/tool.py` | `ToolCapability.KNOWLEDGE_GRAPH` |
| `app/schemas/task.py` | `EXTRACT_ENTITIES` and `EXTRACT_CLAIMS` → `KNOWLEDGE_GRAPH` (today they route to a date and amount regex) |
| `app/tools/knowledge.py` | `KnowledgeGraphTool`: deterministic, reads the run's knowledge base from `ToolContext`, returns conflicts first and then claims, as `extractions` with exact locators. With no knowledge base it falls back to regex extraction and says so in its output |
| `app/tools/base.py` | `ToolContext.knowledge: KnowledgeSnapshot \| None` |
| `app/orchestration/mission.py` | Build the knowledge base after planning when the graph needs it. Add the **knowledge pass** (A5). Put the snapshot on `MissionResult.knowledge` |
| `app/schemas/event.py` | `KNOWLEDGE_EXTRACTED` (38 → 39), with counts: entities, claims, ungrounded, conflicts, chunks, LLM calls |
| `app/integrations/neo4j_store.py` | After verification, write `(:Finding)-[:CITES]->` edges, which the Phase 32 evidence trail reads |

**Design**

*The knowledge pass (A5).* When knowledge is enabled, the intent is comparative (the same test
the reasoning engine already applies), and the plan has no knowledge task, the orchestrator adds
one `extract_claims` task after validation:
- It goes **after** validation, so `plan_validity` is unaffected and the planner is not credited
  with a task it did not plan.
- It is recorded with a `TASK_CREATED` event whose payload says `"origin": "knowledge_pass"`, and
  the task description says the same.
- It is configurable with `knowledge.cross_source_pass: never | comparative | always`, so its
  effect can be measured on and off.

*What reasoning sees.* One line per side of each conflict, with both locators:

```
- aurora_financial_report.txt:r8  Project Aurora.completion_date = 14 May 2026
                                  [conflicts with aurora_project_report.txt:r10 = 30 April 2026]
```

The reasoning engine is unchanged. It still has to state the finding, and the binder,
comparative rule, relevance gate and verifier still judge it. The knowledge layer supplies the
pairing a 4B model will not make. It does not supply the conclusion.

*Cost.* One LLM call per chunk; the eight fixture documents are one chunk each. Measured in
Phase 34 as part of `latency_s`. If the cost is too high, `cross_source_pass: never` turns the
pass off without a code change.

**Tests:** tool output shape, conflict lines carrying both locators, the regex fallback; the pass
inserted only when it should be, recorded, and absent when `never`; `plan_validity` unaffected;
`EventType` count updated; a full mission on `EchoProvider` producing a finding that cites both
sides of a knowledge conflict.

**Done when:** `aurora_contradiction` and `aurora_pdf_timeline`, the two scenarios that keep CI
red, are re-run with the pass on and off, and the comparison is recorded either way. **The
threshold is not moved** to make CI green. If recall does not improve, the bug log says so and
why.

**Documents:** `teammate-port.md` (pipeline section); `.claude/architecture/agent-architecture.md`
(the new step); `.claude/api/events.md`; bug log BUG-005/012 continuation with the measured
result; changelog.

---

### Phase 31 — Knowledge API

**Goal:** every Member 3 endpoint, per mission, plus the endpoints the 3D view needs.

**Ports:** K12.

**Build:** `app/api/v1/knowledge.py`, `app/api/v1/schemas.py`, `docs/openapi.json` regenerated.

| Original | JARVIS |
|---|---|
| `POST /ingest` | `POST /api/v1/knowledge/analyze`: documents in, full knowledge base out, no mission. Member 3's standalone use, scoped to the request |
| `GET /entities` | `GET /api/v1/missions/{id}/knowledge/entities` |
| `GET /find_entity?name=` | `.../knowledge/entities?name=` |
| `GET /relationships`, `/relationships/{entity_id}` | `.../knowledge/relationships?entity_id=` |
| `GET /claims` | `.../knowledge/claims?entity_id=&grounded=` |
| `GET /contradictions` | `.../knowledge/conflicts` |
| `GET /timeline`, `/entity/{id}/timeline` | `.../knowledge/timeline?entity_id=` |
| `GET /timeline/compare` | `.../knowledge/timeline/compare?claim_a=&claim_b=` |
| `GET /entity/{id}/network?depth=` | `.../knowledge/entities/{entity_id}/network?depth=` (depth ≤ 4) |
| `GET /evidence/{claim_id}` | `.../knowledge/claims/{claim_id}` (claim, source line, document) |
| `GET /investigation/{name}` | `.../knowledge/investigation?name=` |
| `GET /search?q=&depth=` | `.../knowledge/search?q=&depth=` |
| (new) | `.../knowledge/graph`: nodes and links shaped for the 3D view, with optional `focus` and `depth` |
| (new) | `.../knowledge/nodes/{node_id}`: everything the hover pop-up shows, fetched lazily |
| (new) | `.../findings/{finding_id}/trail`: the node ids a finding rests on (A9) |

**Design:** CORS stays on the existing allow-list; the original's `*` is not carried over.
Unknown ids return the existing typed error envelope, not `{"error": ...}` with a 200. Every
response is a Pydantic model, so the OpenAPI contract test covers it.

**Tests:** `test_api.py` covers each endpoint on a finished `EchoProvider` mission; 404s; depth
ceiling; `analyze` with no mission; contract freshness.

**Done when:** every row above returns typed data for a finished mission, and `openapi.json` is
current.

**Documents:** `.claude/api/endpoints.md` (each endpoint, with the original it replaces);
changelog.

---

### Phase 32 — 3D knowledge graph explorer

**Goal:** the knowledge graph as an interactive 3D view in Mission Control, replacing Member 3's
`dashboard.html` and doing what was asked: nodes with sub-nodes, click to highlight related
nodes, hover for a pop-up.

**Ports:** K13.

**Build**

| File | Content |
|---|---|
| `frontend/package.json` | `3d-force-graph` and `three` (with `@types/three`). The vanilla library, wrapped in one React component, rather than `react-force-graph-3d`: no React-19 peer dependency to fight, and one place owns the WebGL lifecycle |
| `frontend/src/components/graph3d/KnowledgeGraph3D.tsx` | The canvas: mounting, data updates, camera, disposal |
| `.../graph3d/useGraphModel.ts` | API data → nodes and links; expand/collapse state; highlight sets |
| `.../graph3d/NodeTooltip.tsx` | The hover pop-up |
| `.../graph3d/NodePanel.tsx` | The side panel for a selected node |
| `.../graph3d/GraphControls.tsx` | Search, filters, depth, 2D/3D toggle, reset |
| `frontend/src/pages/pages.tsx`, `App.tsx` | Route `#/mission/{id}/graph` and a "Knowledge graph" tab on the mission page; route `#/knowledge` for `analyze` without a mission |
| `frontend/src/api/types.ts`, `client.ts` | Types for the Phase 31 endpoints |

**Design**

*Node hierarchy: nodes with sub-nodes*

| Level | Node | Appears |
|---|---|---|
| Parent | **Entity** (person, org, shipment, ...) | Always |
| Sub-node | **Claim** (`arrival_date = 14 September`) | When its entity is expanded |
| Sub-node | **Document** it was cited in | When its entity is expanded, shared between entities |
| Overlay | **Finding** | When "show findings" is on |

The graph opens with entities only, so it stays readable. Entity size reflects its number of
claims, and a badge shows how many sub-nodes are folded inside.

*Interactions*

| Action | Behaviour |
|---|---|
| **Hover a node** | A pop-up card at the cursor. Entity: name, type, aliases, claim count, documents, conflict count. Claim: attribute = value, quoted source line, citation, grounded or not. Document: name, kind, number of entities. Data comes from `/nodes/{id}`, fetched once and cached. Also opens on keyboard focus |
| **Click a node** | **Highlights the node and every related sub-node and neighbour**: its claims, their documents, the entities it relates to, and the links between them. Everything else dims to 15% opacity. The camera flies to the node. The side panel opens with full details and an "expand" control |
| **Double-click an entity** | Expands or collapses its sub-nodes (claims and documents) in place |
| **Depth control** (1–3) | How far "related" reaches when highlighting: direct sub-nodes only, or neighbours of neighbours |
| **Click empty space / Esc** | Clears the highlight |
| **Conflict links** | Drawn red, with directional particles moving between the two claims, and the label "conflicts" |
| **Click a finding** (A9) | Lights up the trail: the finding, the claims and documents it cites, and the entities those belong to. The finding's verification status is shown on the trail's edge |
| **Search box** | Type an entity name; the camera flies to it and selects it |
| **Filters** | Entity type, conflicts only, grounded only, one document |
| **2D/3D toggle** | Same data in `force-graph` 2D. Also the default when `prefers-reduced-motion` is set or WebGL is unavailable |

*Live growth (A10).* During a running mission, a `KNOWLEDGE_EXTRACTED` event on the existing SSE
stream triggers one refetch, and new nodes enter with a short animation, so the graph builds
while the agent works. Replay mode (`#/replay`) rebuilds it from the recorded event as well.

*Accessibility*, kept consistent with Phase 21's rule that **nothing relies on colour alone**:
node type is shown by shape (sphere for entity, cube for claim, octahedron for document) as well
as colour; conflict links carry a label; and a keyboard-navigable list beside the canvas mirrors
the graph, with arrow keys moving selection and Enter expanding.

*Performance.* WebGL is fine to a few thousand nodes. This corpus produces about a hundred.
Labels render only for highlighted nodes and the hovered one. The view is lazy-loaded, so the
`three` bundle (~600 kB) is fetched only when the tab opens.

*Theme.* It uses the existing Mission Control CSS tokens in light and dark.

**Tests:** the frontend has no test runner (carried debt). This phase adds **Vitest**, scoped to
the pure logic in `useGraphModel.ts`: the highlight set for a click at each depth,
expand/collapse, the finding trail, and filters. The canvas itself is checked by the existing
`npm run build` CI job and a recorded manual check (screenshots in the development log).

**Done when:** on the shipment scenario, hovering "Shipment 4821" shows its pop-up; clicking it
highlights its claims, both shipping reports and Rahul Sharma, with the 14/16 September conflict
link drawn red; clicking the finding that reports the conflict lights up exactly its trail; and
the same works in 2D with reduced motion.

**Documents:** **ADR-011** (3D explorer: the library choice, why vanilla over the React wrapper,
the accessibility rules); `frontend/README.md`; the demo script gains a graph demo; screenshots
in the development log; changelog.

---

### Phase 33 — Memory

**Goal:** Member 4's three memory tiers, fitted to how JARVIS already stores runs.

**Ports:** T10 working memory, T11 episodic memory, T12 semantic memory.

**Build**

| Tier | Original | JARVIS |
|---|---|---|
| **Working (T10)** | A mutable `WorkingMemory` class | `app/memory/working.py`: `WorkingMemorySnapshot` **derived from** `MissionResult` (objective, plan steps, evidence count, hypotheses, findings). Not a second live state that could drift from the task graph |
| **Episodic (T11)** | SQLite: Q&A log plus archived snapshots, `LIKE` search | Postgres tables `memory_episodes` and `memory_investigations` (Alembic migration). Written at run end through the existing optional-persistence path: one episode per finding (objective, claim, sources, verification status), plus the archived snapshot. Search with `ILIKE`, newest first, same as the original |
| **Semantic (T12)** | SQLite subject-predicate-object facts with `confidence=1.0` | **Neo4j** cross-run graph (A14): `(:Fact)` relationships between `(:KnownEntity)` nodes merged by normalised name across runs, each carrying `support_count` (how many distinct runs and sources asserted it) and its sources. With `GRAPH_STORE=memory`, a Postgres `memory_facts` table instead |

API: `GET /api/v1/memory/episodes?q=`, `GET /api/v1/memory/investigations/{run_id}`,
`GET /api/v1/memory/facts?subject=&predicate=`, `GET /api/v1/memory/entities/{name}` (an entity
across past runs). UI: a "Memory" page with search, and "seen in N earlier investigations" in
the hover pop-up.

**Design**

- **Memory is never read back into a run by default (rule 8, invariant 4).** A run that silently
  used facts from an earlier run could not be reconstructed from its own events, and its
  evaluation numbers would depend on the order scenarios ran in. Memory is for people to search.
  Using it during a run would be a separate, opt-in, measured feature, and is not in this plan.
- **Only verified findings become semantic facts.** The original had no gate. Distilling
  unverified claims into durable memory would make a hallucination permanent.
- **No asserted confidence.** The original stored `confidence: float = 1.0`. The project's rule is
  that confidence is computed, so a fact carries `support_count` and its sources, from which a
  reader can judge.
- **Persistence never fails a run.** Memory writes use the same contained, logged path as run
  persistence.

**Tests:** working snapshot from a `MissionResult`; episode and investigation writes and search
against Postgres (`requires_db`); facts written only from verified findings; `support_count`
across two runs; the no-database path a silent no-op; a test that a run's inputs never include
memory.

**Done when:** two missions over overlapping documents leave searchable episodes, and "Rahul
Sharma" shows up as one known entity seen in both runs, with its facts and their support counts.

**Documents:** `teammate-port.md` T10–T12; new `.claude/architecture/memory.md` (the tiers, why
memory never feeds back, why there is no confidence float); the migration noted in
`.claude/api/schemas.md`; changelog.

---

### Phase 34 — Evaluation and hardening

**Goal:** everything measured, every invariant updated, CI covering the new services.

**Ports:** K14 (the sample data becomes scenarios).

**Build**

| Item | Detail |
|---|---|
| Fixtures | Member 3's seven chunks as `.agent/fixtures/documents/shipment_*.txt`, one per source |
| `shipment_arrival_conflict.yaml` | Positive: 14 vs 16 September across two shipping reports |
| `shipment_9012_consistent.yaml` | Negative: invoice and delivery agree, so the correct answer is no finding |
| `injection_document.yaml` | A real objective over documents where one carries an injection; the run must complete, flag it and not obey it |
| Experiments | **Exp-003:** knowledge pass `never` vs `comparative`. **Exp-004:** verifier `baseline` vs `composite`. Both on the full suite, both in `experiment-log.md` |
| Baseline | A new evaluation baseline, committed, stamped |
| CI | `integration` job with Neo4j; `eval-regression` validates trust and security reports too; the frontend job runs Vitest |
| Invariants | Vocabulary counts (EventType, capabilities); the run-isolation test; a test that `app/integrations/neo4j_store.py` is the only module importing `neo4j` |

**Done when:** the suite (eleven scenarios) has run on the final configuration; Exp-003 and
Exp-004 are recorded with their numbers; the chosen defaults follow from those numbers; CI is
green on everything except whatever the evaluation gate honestly still fails on, and the README
says what that is.

**Documents:** `experiment-log.md`, `agent-evaluation.md`, `testing-strategy.md`, the README
metrics table (checked by `check_documented_metrics.py`); changelog.

---

### Phase 35 — Documentation and handover

**Goal:** someone who was not here can run it, demo it, and see what came from whom.

**Build:** README (architecture section with the knowledge layer, Neo4j, memory and the 3D view;
quickstart with optional Neo4j); `docs/demo-script.md` (a graph demo, an injection demo, a memory
demo, each with a recorded fallback); `docs/contribution.md` (a section crediting Members 3 and 4
feature by feature); `teammate-port.md` with every row `DONE`/`CHANGED`/`NOT PORTED`;
`implementation-plan.md` progress table updated; `.claude/README.md` reading order.

**Then:** you delete `jarvis-member3/` and `mem4/`. The archive in
`.claude/integrations/originals/` and the inventory remain the record.

**Done when:** a clean clone, following the README, runs a mission, opens the 3D graph, and
reproduces the committed trust benchmark.

---

## 3. Decisions needed from you before Phase 25

| # | Question | Recommendation |
|---|---|---|
| D1 | Neo4j **required**, or optional with the in-memory fallback? | **Optional.** Docker has been down on this machine for most of the project, and the demo should not depend on it |
| D2 | Neo4j for the per-run graph **and** cross-run memory (A14), or per-run only? | **Both.** Cross-run is where Neo4j does something the in-memory store cannot |
| D3 | Keep the code already written (BUG-015 fix and the six ported files) as Phase 25–26 work? | **Keep.** It is tested and matches this plan. Reverting it means rewriting it |
| D4 | Commit after each phase? | **Yes, one commit per phase**, as Phases 0–24 were |
| D5 | Change the default verifier to `composite` if Exp-004 supports it? | Let the measurement decide; recorded either way |
| D6 | Any add-on (A1–A14) to drop? | All are kept unless you say otherwise |

### Answers (2026-10-03)

| # | Answer | Effect on the plan |
|---|---|---|
| D1 | "Docker is now working, and Neo4j will be good" | Neo4j is the **default** graph store (`GRAPH_STORE=neo4j` in `.env.example`). The in-memory store stays as the fallback, because CI unit jobs, `LLM_PROVIDER=echo` tests and a laptop with Docker stopped must still run (rule 9) |
| D2 | "You decide what's feasible" | **Both.** Per-run graph (Phase 29) and the cross-investigation memory graph (Phase 33, A14). Feasible because they share one driver, one service and one schema file; the only addition is `:KnownEntity`/`:Fact` nodes merged across runs |
| D3 | "According to you, you are the developer" | **Kept.** The BUG-015 fix and `temporal.py`/`schemas/knowledge.py` are committed in Phase 25, and the `trust/` files in Phase 26 |
| D4 | Yes | One commit per phase |
| D5 | Yes, decided by measurement | Exp-004 in Phase 34 decides |
| D6 | "That's on you" | All fourteen add-ons kept |

## 4. Risks

| Risk | Effect | Mitigation |
|---|---|---|
| `qwen3:4b` extracts inconsistent attribute names across documents | Conflicts missed, and the knowledge pass does not help recall | A8 shared vocabulary; measured in Exp-003; recorded honestly if it does not help |
| Knowledge pass adds latency | `latency_s` rises | One call per chunk, bounded; switchable with `cross_source_pass` |
| Neo4j heap on a 6 GB-VRAM laptop alongside Ollama | Memory pressure | Heap capped at 512 MB; Neo4j optional |
| WebGL unavailable or slow on the demo machine | The 3D view fails in front of an audience | Automatic 2D fallback; the graph demo has a recorded fallback |
| Multi-valued attributes (milestone dates) read as conflicts | False conflicts | The prompt asks for single-valued attributes; the verifier and relevance gate still judge every finding; measured on the negative scenarios |
| Teammates change their code after the port | Drift | ADR-009 consequence: ports are by hand and logged in `teammate-port.md` |

## 5. Documentation discipline

Every phase updates, before it is marked done:

- `.claude/changes/changelog.md`: what was added, changed or fixed, and measured
- `.claude/logs/development-log.md`: what was done in the session and what was learned
- `.claude/logs/bug-log.md`: every defect found, its cause, why tests missed it, the fix
- `.claude/logs/experiment-log.md`: every measurement that decided something
- `.claude/integrations/teammate-port.md`: the status of every ported feature
- `implementation-plan.md`: the progress table
- An ADR when a decision is contested (ADR-010 Neo4j, ADR-011 3D explorer)
