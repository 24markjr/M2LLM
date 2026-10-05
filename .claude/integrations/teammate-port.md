# Porting Members 3 and 4 into JARVIS

**Started:** 2026-10-03
**Status:** in progress. Each feature row below carries its own status.
**Decision record:** [ADR-009](../decisions/ADR-009-port-teammates-in-process.md)
**Original source, verbatim:** [`originals/`](originals/), archived before the extracted folders
(`jarvis-member3/`, `mem4/`) were deleted. When this document and the archive disagree about what
the original did, the archive is right and this document has a bug.

---

## Why a port, not a wrapper

Both teammates built working standalone projects. Neither could be imported or called as-is
without breaking an invariant this repository tests for:

| Their code | Invariant it breaks | Test that would fail |
|---|---|---|
| Member 3 `extractor.py` calls Ollama directly with `requests`, hard-coded URL and model `qwen2.5:7b` | 1. The model is reached only through `app/llm/` | `test_llm_isolation.py::test_no_http_client_outside_the_llm_and_integration_packages` |
| Member 3 `db.py` uses one global SQLite file (`jarvis_knowledge.db`) shared by every ingest | 4. A run is reconstructable from its own events. Claims from one mission appeared in the next mission's contradictions | none existed. This one needed a new test |
| Member 4 verifier falls back to word overlap when scikit-learn is missing, and the overlap passes a wrong date as `SUPPORTED` | 5. No fabricated behaviour. The check silently gets weaker | none existed. Measured below |
| Member 4 memory stores a bare `confidence: float` on each fact | "Confidence is computed, never asserted" | `test_invariants.py::test_a_bare_confidence_number_cannot_be_constructed` covers `Confidence`, not a raw float. Same rule, different type |
| Both use `print()` for errors and `sys.path.insert` hacks | ruff `T20`; mypy strict | lint |

Neither teammate is at fault here. They built for their own scope and to their own runtime. The
port keeps **the same logic** and changes **where it lives and what it is allowed to touch**.

---

## What was measured before porting

Run on 2026-10-03 against the teammates' own code, unmodified, from a scratch copy.

### Member 4's benchmark (`eval/run_benchmark.py`, 60 cases)

| | scikit-learn installed | scikit-learn missing (the JARVIS venv) |
|---|---|---|
| Overall accuracy | **60/60 (100%)** | 46/60 (76.7%) |
| supported | 30/30 | 30/30 |
| insufficient_evidence | 20/20 | **6/20** |
| contradiction | 10/10 | 10/10 |
| Hallucination rate (false confidence) | 0.0% | 0.0% |
| Injection detection (14-case suite) | 100% | 100% |
| Avg verification latency | 1.78 ms | - |

The benchmark is synthetic and was generated to exercise exactly the conflict rule the verifier
implements (clock times on a shared shipment ID). 100% on it shows the code does what it says.
It does not show that it generalises.

### Member 4's verifier on the Member 3 shipment sample

Evidence pool: `shipping_report_a.pdf` p4 ("arrived on 14 September") and `shipping_report_b.pdf`
p7 ("arrived on 16 September").

| Claim | scikit-learn | No scikit-learn |
|---|---|---|
| arrived 14 September | SUPPORTED (0.55) | SUPPORTED (1.00) |
| arrived **20 September** (wrong) | **UNSUPPORTED** (0.34), not CONTRADICTED | **SUPPORTED** (0.83) |
| the reports give 14 and 16 September | SUPPORTED (0.47) | SUPPORTED (0.67) |
| "was **not** delivered to Mumbai" | UNSUPPORTED (0.27) | **SUPPORTED** (0.57) |

Two conclusions shaped the port:

1. The conflict rule only fires on clock times (`11:40 AM`). A wrong **date** is never
   `CONTRADICTED`.
2. Without scikit-learn the verifier passes a wrong date and a negation. In JARVIS the fallback
   is therefore never reachable by a missing dependency (see T2).

---

## Feature inventory

Status legend: `TODO` · `DONE` · `CHANGED` (ported with a stated deviation) · `NOT PORTED` (with
the reason).

### Member 3 — knowledge graph and retrieval intelligence

| ID | Feature | Original (file) | JARVIS location | Status |
|---|---|---|---|---|
| K1 | LLM extraction of entities, relationships, claims | `extractor.py` | `app/intelligence/knowledge/extraction.py`, prompt `.agent/prompts/knowledge.md` | CHANGED. Through `LLMProvider`; values and entity names grounded (A6); CSV without a model (A7); names carried across chunks (A8); bounded |
| K2 | Entity resolution by case-insensitive name | `db.py:find_or_create_entity`, `resolve.py` | `app/intelligence/knowledge/store.py` | CHANGED. Wider name normalisation; unextracted entities created, not stored as raw names |
| K3 | Relationship linking, unknown endpoints skipped | `resolve.py` | `store.py` | CHANGED. Endpoints resolve across the run, not the chunk; skips counted |
| K4 | Claim storage with source document + page | `resolve.py`, `db.py` | `store.py`, `app/schemas/knowledge.py` | CHANGED. Tool-style citations; identical claims stored once; per run, not global |
| K5 | Knowledge graph, N-hop neighbourhood | `graph.py` (NetworkX) | `app/intelligence/knowledge/graph.py`; `app/integrations/neo4j_store.py` | DONE. Memory (BFS) and Neo4j (variable-length `RELATES` path), one test suite |
| K6 | Contradiction detection by (entity, attribute) | `contradictions.py` | `app/intelligence/knowledge/conflicts.py` | CHANGED. Values compared by kind (date, number, text); grounded claims only |
| K7 | Timeline with before/after/same labels | `timeline.py:build_timeline` | `app/intelligence/knowledge/timeline.py` | CHANGED. No invented year (inferred for ordering, flagged); date-valued claims included |
| K8 | Compare two claims temporally | `timeline.py:compare_events` | `timeline.py` | CHANGED. Same labels; different precision is `UNKNOWN` |
| K9 | Hybrid search with explainable score | `retrieval.py` | `app/intelligence/knowledge/search.py` | CHANGED. Same score and reasons; no longer returns every claim |
| K10 | Investigation aggregate for one entity | `main.py:/investigation/{name}` | `app/intelligence/knowledge/base.py` | DONE. One shared aggregate over either store |
| K11 | Evidence lookup for a claim | `main.py:/evidence/{claim_id}` | `base.py`; `neo4j_store.py` | DONE on both stores |
| K12 | REST API (14 endpoints) | `main.py` | `app/api/v1/knowledge.py` | CHANGED. All 14 endpoints per mission, typed errors, CORS on the allow-list; plus graph, node detail, finding trail; `analyze` replaces `/ingest` and stores nothing |
| K13 | Browser dashboard | `dashboard.html` | `frontend/src/components/graph3d/`; `#/mission/{id}/graph`, `#/knowledge` | CHANGED. Per mission, 3D (2D fallback) instead of a static 2D network; entities with claims and documents as sub-nodes; click lights related nodes, hover pop-up, finding evidence trail; live refresh on SSE; ADR-011; since Phase 36 also their three other modes - hybrid search, timeline, all contradictions - and the investigate card, all linked to the graph |
| K14 | Sample data (7 chunks) and loader | `sample_data.json`, `load_sample.py` | `.agent/fixtures/documents/shipment_*.txt`; scenarios `shipment_arrival_conflict`, `shipment_9012_consistent` | CHANGED. Text verbatim, one document per source; the loader is the evaluation runner (a scenario names its documents); a planted-injection note added for `injection_document` |

### Member 4 — memory, trust, security, evaluation

| ID | Feature | Original (file) | JARVIS location | Status |
|---|---|---|---|---|
| T1 | TF-IDF relevance scoring | `trust/verifier.py:relevance_scores` (scikit-learn) | `app/intelligence/trust/tfidf.py` (no dependency) | DONE. Parity with scikit-learn 1.9.1: max difference 4.4e-16 over 60 claims x 58 documents |
| T2 | Word-overlap fallback | `trust/verifier.py:_word_overlap_score` | `tfidf.py`, reachable only on an empty vocabulary | CHANGED. Reachable only on an empty vocabulary, never by a missing package |
| T3 | Claim verification, 4 statuses | `trust/verifier.py:verify_claim` | `app/intelligence/trust/lexical.py` | CHANGED. Same procedure and thresholds; dates conflict too (A4) |
| T4 | Entity-aware conflict rule (shared ID, disjoint times) | `trust/verifier.py:_conflicts` | `lexical.py` | CHANGED. Adds disjoint dates; times compared by minute; years in dates are not ids |
| T5 | Answer-level hallucination evaluation | `trust/hallucination_evaluator.py` | `app/intelligence/trust/answer.py`; `synthesis/grounding.py` | DONE. Logic unchanged. Since Phase 37 it checks every report's model-written paragraphs, sentence by sentence (their original was never wired into anything either) |
| T6 | Verifier as a JARVIS `VerificationProvider` | (none; the seam is Member 1's) | `app/integrations/verification.py` | DONE. `LexicalVerifier` and `CompositeVerifier`; `VERIFICATION_PROVIDER=lexical|composite` |
| T7 | Prompt-injection scanner, 5 categories, severity | `security/injection_guard.py` | `app/security/injection.py` | CHANGED. Original 21 patterns and severity rule verbatim (tested against the archive); 5 JARVIS patterns added separately; scanned on every mission and upload, flag never drops |
| T8 | Safe prompt construction (`<document>` wrapping) | `security/injection_guard.py` | `app/security/injection.py` | CHANGED. Wrapper escapes `</document>`; used in the verification (v2) and reasoning (v5) prompts |
| T9 | 14-case adversarial security suite | `security/security_test_suite.py` | `.agent/evals/security/injection_cases.yaml`, `app/evaluation/security.py` | DONE. Their 14 cases verbatim plus 13; 27/27, run by `eval-trust` |
| T10 | Working memory | `memory/working_memory.py` | `app/memory/distill.py:working_snapshot` | CHANGED. Derived from the finished `MissionResult`, not a second live state; archived with the run |
| T11 | Episodic memory (Q&A log, archived investigations, keyword search) | `memory/episodic_memory.py` (SQLite) | `app/memory/episodic.py`; Postgres `memory_episodes`, `memory_investigations` | CHANGED. One episode per finding, every status kept; same `ILIKE` search, newest first, 5 by default, wildcards escaped |
| T12 | Semantic memory (subject-predicate-object facts) | `memory/semantic_memory.py` (SQLite) | `app/memory/semantic.py`; `neo4j_store.py:Neo4jSemanticMemory` | CHANGED. Facts only from verified findings; `support` (runs and lines) instead of `confidence=1.0`; entities merged across runs; Neo4j or Postgres by configuration; never read back into a run |
| T13 | Synthetic benchmark generator | `eval/generate_benchmark.py` | `app/evaluation/trust.py` | DONE. Byte-identical data from seed 42, checked by test |
| T14 | Benchmark runner and dashboard | `eval/run_benchmark.py` | `python -m app.cli eval-trust`; `scripts/check_trust_reports.py` | CHANGED. Typed, stamped report, committed and re-run by CI. Per-case episodic logging was **not** brought back: memory (Phase 33) records missions, and logging 60 synthetic benchmark cases as past investigations would fill it with things no investigation found |
| T15 | Benchmark data (60 cases, 58 documents) | `eval/benchmark.json`, `eval/evidence_corpus.json` | `.agent/evals/trust/` | DONE. Copied verbatim |
| T16 | `contradiction_test.py` demo | `trust/contradiction_test.py` | `tests/unit/test_trust.py` | CHANGED. The original demo itself returns SUPPORTED (see T16 below); kept as a test of that, plus a working variant |
| T17 | `member4_steps1-5/` | an older copy of five files | superseded by `Mem-4/`, not ported | NOT PORTED |

---

## How each original feature works

Recorded in enough detail to re-derive the behaviour without the archive. Constants are exact.

### K1 — extraction (`extractor.py`)

- `POST http://localhost:11434/api/generate`, model `qwen2.5:7b`, `stream: false`,
  `format: "json"`.
- One prompt per text chunk asks for three lists in this shape:
  `{"entities":[{"type","name"}], "relationships":[{"subject","predicate","object"}],
  "claims":[{"entity","attribute","value"}]}`. Entity types: `PERSON, ORG, LOCATION, DATE,
  PRODUCT, SHIPMENT`. Its example claim is `entity="Shipment 4821", attribute="arrival_date",
  value="14 September"`.
- If the response has no `response` key, or it is not valid JSON, it prints the error and returns
  three empty lists. Missing keys in items default to `""` (entity type defaults to `"UNKNOWN"`).
- No locator below page level. The caller supplies `source_document` and `page` for the whole chunk.

### K2–K4 — resolution and storage (`resolve.py`, `db.py`)

- Four SQLite tables: `entities(entity_id PK, type, name, source_document, source_page)`,
  `entity_sources(entity_id, source_document, source_page, UNIQUE all three)`,
  `relationships(relationship_id PK, subject, predicate, object, source_document, source_page)`,
  `claims(claim_id PK, entity, attribute, value, source_document, source_page)`.
- **Resolution:** `LOWER(name) = name.strip().lower()`. A match reuses the `entity_id`, otherwise
  it creates `ENT-<8 hex>`. Every mention adds an `entity_sources` row.
- **Relationships:** both endpoints must be names extracted in the same chunk. Otherwise the
  relationship is skipped ("rather than store garbage"). IDs are `REL-<8 hex>`.
- **Claims:** the entity is mapped to an ID when its name was extracted in the same chunk.
  **Otherwise the raw name string is stored as the entity.** IDs are `CLM-<8 hex>`.
- One global database file for every ingest, ever.

### K5 — graph (`graph.py`)

- Rebuilds a `networkx.DiGraph` from SQLite on every call. Nodes are entities; edges are
  relationships carrying `predicate`, `source`, `page`.
- `get_entity_network(entity_id, depth=2)`: `ego_graph` on the **undirected** view with
  `radius=depth`. Returns nodes that have a name, and directed edges whose endpoints are both in
  that node set. An unknown entity returns `{"error": "entity not found"}`.

### K6 — contradictions (`contradictions.py`)

1. Deduplicate claims on `(entity, lower(attribute), lower(value), source_document, source_page)`.
2. Group on `(lower(entity), lower(attribute))`.
3. A group with more than one distinct `lower(strip(value))` is a contradiction:
   `{entity, attribute, conflicting_claims: [{value, source, page}]}`.
4. Never decides which side is right.

### K7–K8 — timeline (`timeline.py`)

- Date formats tried in order: `%d %B`, `%d %B %Y`, `%B %d`, `%B %d, %Y`, `%d/%m/%Y`, `%d-%m-%Y`.
- **Every parsed date is forced to year 2026** with `dt.replace(year=2026)`, including dates
  that carried their own year.
- Timeline events are claims whose attribute contains `date` or `time`. They are sorted by the
  parsed ISO date, with unparseable values last (`"9999"`).
- `relation_to_previous`: `None` for the first event, `UNKNOWN` if either date did not parse,
  `SAME_TIME_AS` if equal, otherwise `AFTER`.
- `compare_events(a, b)` returns `A_BEFORE_B`, `A_AFTER_B`, `SAME_TIME`, or `UNKNOWN` with
  a reason.

### K9 — hybrid search (`retrieval.py`)

1. Tokens: `[a-zA-Z0-9]+`, lowercased.
2. Entity match: for each token of at least 3 characters, entities whose name `LIKE %token%`.
3. Graph expansion: add every node in each matched entity's network at `depth` (default 1).
4. Score every claim: **+3** if its entity was matched directly, **+1** if connected through the
   graph, **+1 per overlapping token** between the query and `attribute + value`, and **+1 if it
   has a source document**. Each point records a reason string.
5. Return claims with a score above 0, sorted by score descending.

Because every stored claim has a source document, step 4's last rule gives every claim at least
1, so **search always returns every claim**. Recorded as a defect, not a design.

### K10–K12 — API (`main.py`)

| Method | Path | Behaviour |
|---|---|---|
| POST | `/ingest` | `{document_id, content, source_document, page}` → extract, resolve, store. Returns the raw extraction |
| GET | `/entities` | all entities |
| GET | `/find_entity?name=` | `name LIKE %name%` |
| GET | `/relationships` | all |
| GET | `/relationships/{entity_id}` | where subject or object |
| GET | `/claims` | all |
| GET | `/contradictions` | K6 |
| GET | `/timeline` | K7 |
| GET | `/timeline/compare?claim_id_a=&claim_id_b=` | K8 |
| GET | `/entity/{entity_id}/network?depth=2` | K5 |
| GET | `/entity/{entity_id}/timeline` | K7 filtered to one entity |
| GET | `/evidence/{claim_id}` | the claim and `{document, page}` |
| GET | `/investigation/{name}` | first entity matching the name: entity, its sources, network (depth 2), claims, contradictions |
| GET | `/search?q=&depth=1` | K9 |

CORS allows every origin. The investigation endpoint filters contradictions with
`c["entity"] == entity_id.lower()`.

### K13 — dashboard (`dashboard.html`)

A single static page that calls `/contradictions`, `/investigation/{name}`, `/search?q=` and
`/timeline` on `http://127.0.0.1:8000`.

### T1–T4 — verifier (`trust/verifier.py`)

- **Relevance:** `TfidfVectorizer(stop_words="english")` fitted on `[claim] + evidence`, then
  cosine similarity of the claim row against each evidence row. On `ValueError` (empty vocabulary)
  or no scikit-learn: `|tokens(claim) ∩ tokens(evidence)| / |tokens(claim)|`, tokens
  `[a-z0-9]+`.
- **Decision**, with `relevance_threshold=0.2`:
  1. Empty pool → `INSUFFICIENT_EVIDENCE` ("Evidence pool is empty.").
  2. Nothing scoring ≥ 0.2 → `INSUFFICIENT_EVIDENCE`, relevance = best score.
  3. Any relevant item that `_conflicts` → `CONTRADICTED`. Supporting evidence is the relevant
     non-conflicting items; contradicting evidence is listed with `source (p.page)`.
  4. Any relevant item scoring ≥ **0.4** → `SUPPORTED`.
  5. Otherwise → `UNSUPPORTED` ("Related evidence exists but does not directly confirm...").
- **`_conflicts(claim, evidence, relevance)`:** false if relevance < **0.5**. The ID regex
  `\b\d{3,}\b` must share at least one match between claim and evidence. The time regex
  `\b\d{1,2}:\d{2}\s*(?:am|pm)?\b` (case-insensitive) must find times on both sides, normalised by
  lowercasing and removing spaces, and the two sets must be **disjoint**.
- The status enum also defines `PARTIALLY_SUPPORTED`, which `verify_claim` never returns. Only
  T5 produces it.

### T5 — answer evaluation (`trust/hallucination_evaluator.py`)

- Split on `(?<=[.!?])\s+`, verify each sentence with T3.
- Overall: all `SUPPORTED` → `SUPPORTED`; any `CONTRADICTED` → `CONTRADICTED`; any `SUPPORTED` →
  `PARTIALLY_SUPPORTED`; all `INSUFFICIENT_EVIDENCE` → `INSUFFICIENT_EVIDENCE`; otherwise
  `UNSUPPORTED`. Empty answer → `INSUFFICIENT_EVIDENCE`.

### T7–T9 — security (`security/`)

Patterns, case-insensitive, first match per pattern:

| Category | Patterns |
|---|---|
| `override_instructions` | `ignore (all \|the )?(previous\|prior\|above) instructions` · `disregard (all \|the )?(previous\|prior\|above) (instructions\|context)` · `forget (all \|the )?(previous\|prior\|above) instructions` · `new instructions?:` · `\bdo not follow\b` · `override your (instructions\|rules\|guidelines)` |
| `role_manipulation` | `you are now` · `act as (if\|though)` · `pretend (you are\|to be)` · `from now on,? you (will\|must\|should)` |
| `system_prompt_extraction` | `system prompt` · `reveal (your \|the )?(system\|hidden) prompt` · `print (your \|the )?(instructions\|system prompt)` · `what (are\|were) your instructions` |
| `data_exfiltration` | `send (this\|the) (data\|information) to` · `email (this\|the) (data\|information\|conversation) to` · `output (all\|every) (previous\|prior) (message\|conversation)` |
| `tool_call_spoofing` | `<tool_call>` · `\[system\]` · `function_call\s*:` · `execute\s*\(` |

- Severity: `NONE` if no hits. `HIGH` if any hit is `system_prompt_extraction`, `data_exfiltration`
  or `tool_call_spoofing`. Otherwise `MEDIUM`.
- `wrap_untrusted(source, content)` → `<document source="...">\ncontent\n</document>`.
  `build_safe_prompt` puts the blocks between an instruction that document content is data and
  the question.
- Suite: 11 attack documents (override ×3, role ×2, extraction ×2, exfiltration ×2, tool spoof ×2)
  and 3 clean ones. 14/14.

### T10–T12 — memory (`memory/`)

- **Working:** an `investigation_id` (`INV-<8 hex>`), objective, plan steps, evidence seen
  `{source, content}`, hypotheses, findings, `started_at`. `snapshot()` returns them, with
  evidence reduced to a count.
- **Episodic** (SQLite next to the module): `episodic_memory(entry_id, investigation_id,
  question, answer, sources_used JSON, verification_status, created_at)` and
  `investigations(investigation_id, objective, snapshot_json, archived_at)`. `log()`,
  `archive_investigation(snapshot)`, `search(keyword, limit=5)` as `LIKE` on question or answer,
  newest first, `all_entries()`, `clear()`.
- **Semantic** (a second SQLite file): `semantic_memory(fact_id, subject, predicate, object,
  source, confidence REAL, created_at)`. `add_fact(..., confidence=1.0)`, and `query(subject?,
  predicate?)` by exact match.

### T13–T15 — benchmark (`eval/`)

- `random.seed(42)`, 40 base facts. Each fact draws a person, company and location from fixed
  lists, a time with hour 6–20 and minute in {0, 15, 30, 40, 45}, shipment id `1000 + i`, and an
  amount from a fixed list.
- Every fact gets one evidence document. A random 20% get a verbatim duplicate. A random 25% get a
  conflicting copy whose hour is shifted by 1–3.
- Cases: one per fact, `CONTRADICTED` if it was conflicted and `SUPPORTED` otherwise, plus 20
  `INSUFFICIENT_EVIDENCE` cases about shipment `90000 + i` and "Unlisted Person i". Shuffled.
- The runner computes accuracy, a "hallucination rate" (risky cases, meaning expected
  `CONTRADICTED` or `INSUFFICIENT_EVIDENCE`, that came back `SUPPORTED`), per-category accuracy,
  mean latency, and the security suite's detection rate. It logs every case to episodic memory.

---

## Design of the port

Filled in as each part lands. See ADR-009 for the decision itself, and
[`../implementation/integration-plan-phases-25-35.md`](../implementation/integration-plan-phases-25-35.md)
for the phase plan.

### Phase 25 — groundwork (2026-10-03)

**The shared parser, `app/intelligence/temporal.py`.** Both teammates parsed time separately, with
different defects. One module now serves the knowledge layer and the verifier:

| Behaviour | Member 3 | Member 4 | Now |
|---|---|---|---|
| Date formats | six `strptime` formats | none | the six, plus ISO, abbreviations, ordinals, month + year |
| Missing year | forced to 2026 | - | stays missing (`PartialDate.year = None`) |
| Stated year | **also** forced to 2026 | - | kept |
| Two dates equal? | same ISO string | - | `compatible()`: every field known on both sides agrees |
| Clock times | - | lower-cased strings, spaces removed | minutes; `11:40` matches `11:40 AM` |
| Identifiers | - | `\b\d{3,}\b` anywhere | same, with date spans masked so "2026" is not an id |

**BUG-015 and BUG-016**, both in Member 1's code, found while scanning Member 4's verifier. See the
bug log. BUG-015 was a prerequisite: Member 4's verifier scores claim text against evidence text,
and JARVIS was passing evidence as tool summaries ("11 date(s)").

### Phase 26 — trust layer (2026-10-03)

**TF-IDF without scikit-learn (T1/T2).** The original made scikit-learn optional and fell back to
word overlap without it. That fallback cost 14 of 60 benchmark cases and passed a wrong date as
`SUPPORTED`. `tfidf.py` computes the same numbers as `TfidfVectorizer(stop_words="english")`:
the same token pattern, scikit-learn's 318 stop words copied verbatim (BSD-3), raw counts,
smoothed idf `ln((1+n)/(1+df)) + 1`, and L2-normalised rows. **Measured parity:** largest
difference 4.4e-16 across all 60 benchmark claims against all 58 documents. Overlap remains only
for an empty vocabulary, the one case the original reached it with scikit-learn installed.

**The verifier (T3/T4).** Step for step the original, with these thresholds unchanged and
configured in `agent.yaml:verification.lexical`: relevance 0.2, support 0.4, conflict 0.5.
Three deviations:

| Deviation | Effect on the original benchmark | Effect on the shipment probes |
|---|---|---|
| Disjoint **dates** on a shared id also conflict | none: 60/60 before and after (it has no dated claims) | "arrived 20 September" vs one report saying 14 September is now `CONTRADICTED`. Against both shipping reports it stays `UNSUPPORTED`, because relevance (0.34) is under the 0.5 conflict threshold. The threshold was kept rather than tuned to the probe |
| Times compared by minute | none | - |
| Years inside dates are not ids | none | prevents "M1 complete 15 January 2026" from contradicting "M4 ready 30 April 2026" |

**The adapter and the composite (T6).** `LexicalVerifier` maps Member 4's vocabulary onto
JARVIS's in one place (`INSUFFICIENT_EVIDENCE` → `INCONCLUSIVE`, never a pass) and strips the
`doc.txt:r10: ` prefix so a document name is not scored as a matching term. `CompositeVerifier`
gives the lexical check a veto on contradictions only, lets it stand in (marked `degraded`) when
the model reaches no verdict, and otherwise defers to the model. Both opinions are recorded on
every result (`VerificationResult.opinions`) and in the event payload. **The default stays
`baseline`** until Exp-004 (Phase 34) measures `composite` on the full suite. That is decision D5.

**The specifics check (A15), not from Member 4.** Added to `CompositeVerifier` as rule 4 after the
Phase 25 audit (BUG-018): a `SUPPORTED` claim stating a date or figure that none of its cited
evidence contains becomes `PARTIALLY_SUPPORTED`. It lives in its own module,
`app/intelligence/trust/specifics.py`, so `lexical.py` stays a faithful port.

**Confidence.** The TF-IDF score is not used as verdict confidence. It is a similarity, not a
calibrated probability. Verdict confidence uses the baseline's derivation from the number of
distinct documents.

**The benchmark (T13–T15).** `app/evaluation/trust.py` reproduces the generator with a private
`Random(42)` drawing in the original order. **Measured:** byte-identical corpus (58) and cases (60)
to the committed files, checked by test. `python -m app.cli eval-trust` gives **60/60, hallucination
rate 0.000, 1.2 ms per case** (theirs: 60/60, 1.78 ms with scikit-learn). The command exits non-zero
on any false confidence, which is the original dashboard's headline. Per-case episodic logging
returns with memory in Phase 33.

**T16, the contradiction demo.** Member 4's README says `trust/contradiction_test.py`
demonstrates conflict detection. Run against their own current code (2026-10-03) it prints
`SUPPORTED`. Their later shared-identifier safeguard removed the demo's ability to conflict,
because "The incident occurred at 11:40 AM" has no identifier to share. The port behaves
identically, and a test pins that, with a working variant (a shared shipment id) beside it.
Worth telling Member 4.

### Phase 27 — security (2026-10-03)

**Scanner (T7).** Member 4's five categories and 21 patterns are kept verbatim, and a test compares
them against the archived original file rather than a copy. Five patterns are added in a separate
`JARVIS_PATTERNS` list, each for a measured miss: two attacks already in this repository's
adversarial suite went undetected by the originals (a `<|im_start|>system` chat-template spoof, and
"Note to the AI reading this: ..."), and three target JARVIS's own surfaces (closing the
`<document>` wrapper, findings-shaped JSON, a message addressed to the assistant). Measured on the
27-case suite: originals 22/27, with additions 27/27, no false positives on the clean cases or any
of the 14 fixture documents.

**Where it runs.** Every mission scans every document before the first model call
(`INJECTION_DETECTED`, ordered before `INTENT_CREATED`), and every upload returns its scan.
**A flagged document is still read.** Dropping on a match would let anyone delete evidence by
quoting an attack phrase. The report states the flag as a limitation, and Mission Control shows it.

**Wrapping (T8).** `wrap_untrusted` now neutralises a closing `</document>` inside content (the
original let a document end its own block) and a `"` in a source name. Used for each cited text in
the verification prompt (v1 → v2) and for the observations in the reasoning prompt (v4 → v5).
Their effect on the agent suite is in the Phase 27 development-log entry.

**Suite (T9).** `.agent/evals/security/injection_cases.yaml`: Member 4's 14 cases verbatim, the
4 strings `test_adversarial.py` used, 3 JARVIS-surface attacks, and 6 realistic clean texts that
talk about instructions, AI and security without addressing the model. `eval-trust` reports
Member 4's `detection_rate` (correct/total) and, beside it, attack recall, false-positive rate and
category misses, and exits non-zero on any misclassified case.

Full mechanism: `../architecture/security.md`.

### Phase 28 — knowledge core (2026-10-03)

Mechanism and data model: [`../architecture/knowledge-layer.md`](../architecture/knowledge-layer.md).
Live acceptance run: Experiment 005 in `../logs/experiment-log.md`.

**What was kept from Member 3:** the three concepts (entity, relationship, claim); resolution by
name; skipping relationships with unknown ends; grouping conflicts by (entity, attribute) and never
picking a side; the timeline labels and the compare results; the search score and its reasons; the
undirected neighbourhood.

**What changed, and why.** Each change traces to a defect in the original or an invariant here:

| Change | Original behaviour | Evidence |
|---|---|---|
| Model via `LLMProvider`, versioned prompt, constrained output | `requests` to a hard-coded `qwen2.5:7b` | invariant 1 |
| Claim values grounded on their line | anything the model returned was stored | A6; unit tests |
| Entity names grounded | same | Exp 005: "Shipment 482:1", and five names echoed from the known list |
| CSV without a model | CSV went to the model as text | A7 |
| Known names in the next prompt | each chunk extracted cold | A8 |
| Identical claims stored once | duplicates stored | Exp 005 run 1 |
| Conflicts compare by kind | lower-cased strings | "30 April 2026" vs "2026-04-30" conflicted |
| No forced year 2026 | `dt.replace(year=2026)` on every date | unit test with a 2025 date |
| Search adds the source point only after a match | every claim matched | unit test |
| One knowledge base per run | one global SQLite file | unit test: two runs share nothing |
| Sequential ids | `uuid4` | reproducible runs |

**Storage now, Neo4j next.** `InMemoryKnowledgeBase` implements the `KnowledgeBase` protocol, which
the Phase 29 Neo4j store will implement too. K5, K10 and K11 work in memory already, because search
and the investigation aggregate need them.

**Known limit, measured.** A value that is on its line but misread ("according to security logs"
read as `received_by`) passes grounding and makes a false conflict. Conflicts are inputs to
reasoning and verification, never findings by themselves.

### Phase 29 — Neo4j (2026-10-03)

Member 3 rebuilt a NetworkX graph from SQLite on every request. The graph now lives in Neo4j
(ADR-010), per run. The analysis stays the shared Python of Phase 28, and only storage, lookup and
the neighbourhood traversal are Cypher. One test suite runs against Neo4j and the in-memory fallback.
A live extraction of Member 3's sample answered identically from both, and is kept in the local
database as `run_00000000a3a3` for browsing. A contradiction is an edge (`CONFLICTS_WITH`) between
the claims on its two sides, which Member 3's graph never had: there, a claim was not a node.

### Phase 30 — knowledge in the pipeline (2026-10-04)

`extract_entities` and `extract_claims` route to the `knowledge_graph` tool, and the orchestrator
adds a knowledge pass for comparative objectives. Member 3's knowledge base is now built inside a
mission, stored in Neo4j, and handed to reasoning as conflict pairs with both citations. Findings
are recorded in the graph as `CITES` edges.

**What it showed about Member 3's design.** His contradiction rule is same entity, same attribute,
different values. His sample data is built of exactly that. JARVIS's fixtures plant planned-vs-actual
contradictions, which compare different attributes and which the rule cannot see. On them the
knowledge layer extracted 31 claims and paired none. Neither design is wrong; they answer
different questions. Experiment 003 in Phase 34 measures it on shipment scenarios built from his
sample. See the experiment log.

### Phase 31 — knowledge API (2026-10-04)

Every one of Member 3's endpoints, per mission instead of over one global database
(`../api/endpoints.md`, **Knowledge**). The table there maps each original route to its new one.
Deliberate differences: unknown ids are typed 404s, not `{"error": ...}` with a 200; CORS stays on
the allow-list, not `*`; `/ingest` became `POST /api/v1/knowledge/analyze`, which returns a knowledge
base and stores nothing. Added for the 3D view: the graph as nodes and links (claims as sub-nodes of
their entity), a detail record per node for the hover pop-up, and a finding's trail. A mission whose
graph is in Neo4j is still answered after the API restarts.

---

## Add-ons (A1-A15), as built

What the integration added beyond Members 3 and 4's features, from the plan's table in
`implementation/integration-plan-phases-25-35.md`. Every one was built.

| ID | Add-on | Phase | Status |
|---|---|---|---|
| A1 | The verifier reads the cited line, not a tool summary (BUG-015) | 25 | DONE |
| A2 | Observation details match on document and line (BUG-016) | 25 | DONE |
| A3 | Composite verifier | 26 | DONE. The default since Experiment 004 |
| A4 | Date conflicts in the lexical verifier | 26 | DONE |
| A5 | Knowledge pass for comparative objectives | 30 | DONE. Measured in Experiment 003: finds the shipment conflict, which is missed without it |
| A6 | Claim grounding on the source line | 28 | DONE |
| A7 | Deterministic CSV extraction | 28 | DONE |
| A8 | Shared attribute vocabulary across chunks | 28 | DONE. Attribute names still vary between *runs* (Phase 33's memory measurement) |
| A9 | Evidence trail in 3D | 32 | DONE |
| A10 | Live graph growth over SSE | 32 | DONE. Replay does not rebuild the graph |
| A11 | Injection scan at document load | 27 | DONE |
| A12 | Trust and security benchmarks in the harness | 26, 27, 34 | DONE. Re-run by CI since Phase 34 |
| A13 | Three shipment scenarios | 34 | DONE |
| A14 | Cross-investigation graph in Neo4j | 33 | DONE |
| A15 | Specifics check in the composite verifier | 26 | DONE. Extended to numbers in a date's place (BUG-021) |

---

## Member 2 — M2LLM, document ingestion (Phases 38-40)

Ported from their build report (reviewed 2026-10-05; their code was not in this repository). Decision
D7: re-implemented in-process, as Members 3 and 4 were.

| ID | Their feature | Their file | JARVIS location | Status |
|---|---|---|---|---|
| M1 | File classification by extension | `ingestion/classifier.py` | `app/tools/formats.py` | CHANGED. One registry read by the upload check, the file picker and the loader |
| M2 | PDF text, page by page | `parsers/` (PyMuPDF) | `tools/loader.py:load_pdf` (pypdf) | DONE before the port; OCR for scanned pages is Phase 39 |
| M3 | DOCX paragraphs | `parsers/` (python-docx) | `formats.py:load_docx` | CHANGED. Tables too, in document order |
| M4 | TXT, CSV | `parsers/` | `loader.py:load_text` | DONE |
| M5 | XLSX sheets to text | `parsers/` (pandas, openpyxl) | `formats.py:load_xlsx` (openpyxl) | CHANGED. Each sheet a page, so a citation names the sheet; bounded and said to be |
| M6 | Images: orientation and dimensions | `parsers/` (Pillow) | `formats.py:load_image` | DONE, and marked as having no text until OCR |
| M7 | Provenance: file hash, parser, OCR flag | `provenance/tracker.py` (JSONL) | `UploadedDocument.parser/sha256`, logged | CHANGED. In the upload response and the log; stored with retrieval in Phase 40 |
| M8 | OCR (PaddleOCR) | `ocr/` | `app/tools/media.py:read_text` | CHANGED. PaddleOCR's models through RapidOCR; images, scanned PDF pages (rendered with pypdfium2) and video frames; low-confidence lines marked; cached per file (Phase 39) |
| M9 | Normalisation, chunking (600/80) | `normalization/`, `chunking/` | - | TODO, Phase 40 (chunker chosen by measurement) |
| M10 | Embeddings, Qdrant with in-memory fallback, workspace-scoped retrieval | `embeddings/`, `vectorstore/`, `retrieval/` | - | TODO, Phase 40 (pgvector, D9-D11) |
| M11 | Vision-language interface | `vision/` (raises `NotImplementedError`) | `app/tools/media.py:see`, the `vision` role | ADDED, since theirs was unimplemented: a local vision model (`qwen2.5vl:3b`) through `app/llm/`; its output marked `[seen]` and weaker than read text (ADR-012) |
| - | Video, audio | (not in their build) | `formats.py`, `media.py` | ADDED. A timeline of speech (faster-whisper, or a person's transcript), on-screen text and what sampled frames show; audio as timed speech (Phase 39) |
