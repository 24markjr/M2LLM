# The knowledge layer

**Phase:** 28 (2026-10-03); Neo4j storage Phase 29 (ADR-010). Pipeline wiring is Phase 30, the API Phase 31.
**Code:** `app/intelligence/knowledge/`, contracts in `app/schemas/knowledge.py`, prompt
`.agent/prompts/knowledge.md`, policy `agent.yaml:knowledge`
**Ported from:** Member 3's knowledge-graph service (`jarvis-member3/`). Every feature, its
original behaviour and each deviation: `integrations/teammate-port.md`, K1-K11.

---

## What it is for

The reasoning engine reads observations and has to notice, by itself, that one document says
30 April and another says 14 May. A 4B model often does not: that is the recall defect behind
BUG-005 and BUG-012. The knowledge layer does the pairing deterministically. It extracts every
claim as `(entity, attribute, value, citation)`, resolves entity names across documents, and
reports where two sources give the same attribute of the same entity different values. It never
decides which side is right.

## The data model

Member 3's three concepts, unchanged:

- **Entity:** a real-world thing (`PERSON`, `ORG`, `LOCATION`, `DATE`, `PRODUCT`, `SHIPMENT`,
  `OTHER`), resolved across documents, with every spelling (`aliases`) and every mention (`sources`).
- **Relationship:** `subject --predicate--> object`, both resolved entities, with a citation.
- **Claim:** one source asserting one value for one attribute of one entity, with a citation, the
  quoted line, and `grounded`.

The change that matters: **a citation is the same string a tool emits** (`report.txt:r12`,
`report.pdf:p3`), not a document-and-page pair. A claim from the knowledge layer is something the
evidence binder can resolve and the reasoning engine can cite.

## How a run's knowledge base is built

```
documents ──┬─ .csv ──> one entity per row, one claim per cell (no model)            A7
            └─ text ──> chunks of whole lines (≤ chunk_chars) ──> model, one call each  K1
                          lines numbered, wrapped as <document> data
                          + names already used in the run                             A8
                                │
                          entities: kept only if the name is on a line of the chunk     A6
                          claims: grounded against their line, else the chunk; else flagged
                          relationships: both ends must resolve, else skipped and counted
                                │
                          KnowledgeAccumulator (resolution, dedup, ceilings)            K2-K4
                                │
                          detect_conflicts (grounded claims only)                       K6
                                │
                          KnowledgeSnapshot ── InMemoryKnowledgeBase (queries)           K5, K7-K11
```

### Grounding (A6), the property everything else rests on

A model asked to extract can also write. The extractor checks every value against the source:

- A **claim value** must appear on its stated line: the same text after folding case and
  whitespace, a compatible date (`2026-04-30` = `30 April 2026`), or an equal figure
  (`380,000` = `380000`). If it is not there, the other lines of the chunk are searched. If it is
  nowhere, the claim is kept with `grounded=False`, counted, and **excluded from conflicts and the
  timeline.**
- An **entity name** must appear on a line of its chunk. If not, it is not created
  (`entities_ungrounded`). Measured: "Shipment 482:1", and names the model echoed from the
  known-entities list into chunks that never mention them.

**What grounding cannot catch:** a value that is on the line but means something else. Measured
on Member 3's sample, "according to security logs" was extracted as `received_by = security logs`
and produced a false conflict. The knowledge layer's conflicts are therefore **inputs** to
reasoning and verification, never findings by themselves (Phase 30).

### Resolution (K2)

Names resolve by `normalize_name`: casefold, punctuation (such as `#`) removed, whitespace collapsed,
a leading "the" dropped. Member 3 matched `LOWER(name)`, so "Shipment #4821" and "shipment 4821" were
two entities. A claim about an entity that was not extracted creates it; Member 3 stored the raw
name, splitting one entity across an id and a string. Relationship endpoints resolve against the
whole run, not only the chunk they appear in. Ids are sequential (`ENT-001`, `CLM-001`), so a run is
reproducible.

### Conflicts (K6)

Grouped by `(entity, attribute)`. More than one distinct value is a conflict, and every side keeps
all its citations. "Distinct" depends on the kind: `DATE` (all values parse as dates, same if
compatible), `NUMBER` (all single numbers, same if equal), `TEXT` (same after folding). Member 3
compared lower-cased strings, so "30 April 2026" and "2026-04-30" conflicted.

**Multi-valued attributes are the main source of false conflicts.** A `milestone_date` with four
values is four "conflicting" values. The prompt asks for one attribute per single-valued property
(`m1_completion_date`), and the downstream judges still apply.

### Timeline (K7, K8)

A claim is an event if its attribute contains "date" or "time" (Member 3's rule), or if its value
parses as a date. Events are ordered chronologically, unparseable last, and labelled against the
previous one with Member 3's labels (`SAME_TIME_AS`, `AFTER`, `UNKNOWN`). **No year is invented.**
Member 3 forced every date to 2026, including "14 September 2025". For ordering only, a missing year
is inferred as the most common explicit year among the run's events, and the event is flagged
`year_inferred`. "April 2026" against "30 April 2026" is `UNKNOWN`, not the same time.

### Search (K9) and the graph (K5)

The neighbourhood is breadth-first search, ignoring edge direction, within `depth` hops (capped at
4), returning the stored directed edges between the reached entities. That is Member 3's
`ego_graph` result without NetworkX. Search scores every claim +3 (direct entity match), +1
(connected through the graph), +1 per matching word, and +1 (has a source), with a reason per point.
Member 3 gave the last point to every claim, so search returned the whole knowledge base. It is now
only added to a claim that matched something else.

## Bounds (invariant 7)

| Ceiling (`.env`) | Policy (`agent.yaml:knowledge`) | Bounds |
|---|---|---|
| `MAX_KNOWLEDGE_CHUNKS` = 40 | `max_chunks: 12` | model calls per run; the rest are `chunks_skipped` |
| `MAX_KNOWLEDGE_CLAIMS` = 2000 | `max_claims: 400` | claims kept; the rest are `claims_capped` |
| - | `chunk_chars: 3000` | the size of one call's input |
| - | `max_known_terms: 40` | names carried into each prompt |

Every one of those numbers is in `ExtractionStats`, so a knowledge base built from part of its
input is visibly partial.

## Run scoping

Member 3 kept every ingest in one SQLite file, so a later investigation's contradictions included
an earlier one's claims. Here a knowledge base belongs to the run that built it. A test builds two in
one process and checks that they share nothing. Cross-run knowledge is memory (Phase 33), opt-in,
and never read back into a run by default.

## Measured

Experiment 005 (`logs/experiment-log.md`): Member 3's own sample, `qwen3:4b`, two runs. Both found
the planted Shipment 4821 arrival-date conflict with both citations (40-47 s, 7 calls, 0 failed
chunks, 0 ungrounded claims). Both also produced one false conflict from a misread.

## Where it is stored (Phase 29, ADR-010)

`GRAPH_STORE=neo4j` (default) or `memory`. `app/integrations/graph_store.py:open_knowledge_base`
writes the run's snapshot to Neo4j in **one transaction** and returns a `Neo4jKnowledgeBase`, or
returns an `InMemoryKnowledgeBase` when Neo4j is off, unreachable (probed once per process, logged
once) or a write fails. Neo4j never fails a run.

The `KnowledgeBase` protocol is **async**, because the Neo4j driver is. Both stores implement it, and
`tests/unit/test_knowledge_stores.py` runs one suite against both.

**Graph model.** Every node carries `run_id`, and composite uniqueness constraints hold
`(run_id, id)` unique per label:

```
(:Run {run_id, stats})-[:HAS_DOCUMENT]->(:Document {run_id, document_id})
(:Entity {run_id, entity_id, seq, name, key, type, aliases, alias_keys, sources})
    -[:MENTIONED_IN {source}]->(:Document)
    -[:RELATES {relationship_id, seq, predicate, source}]->(:Entity)
    -[:HAS_CLAIM]->(:Claim {run_id, claim_id, seq, attribute, value, source, line, quote, grounded})
                     -[:CITED_IN {source}]->(:Document)
    -[:HAS_CONFLICT]->(:Conflict {run_id, conflict_id, seq, attribute, kind, sides})
(:Claim)-[:SIDE_OF {value}]->(:Conflict)
(:Claim)-[:CONFLICTS_WITH {conflict_id, attribute, kind}]->(:Claim)
```

**Cypher does** storage, listing, lookup by id and by normalised name, and the neighbourhood (a
variable-length `RELATES` path). **Shared Python does** timeline order, search scores, entity ranking
and the investigation aggregate, on data read from either store, so the two cannot disagree.

**Look at a run in the Neo4j Browser** (<http://localhost:7474>, user `neo4j`, password from
`NEO4J_PASSWORD`):

```cypher
MATCH (n {run_id: 'run_00000000a3a3'})-[r]-(m {run_id: 'run_00000000a3a3'}) RETURN n, r, m
```

`run_00000000a3a3` is Member 3's sample, extracted live and kept in the local database on
2026-10-03.

## In a mission (Phase 30)

```
intent -> plan (validated) -> [knowledge pass added?] -> [knowledge built?] -> execute -> reason ...
```

1. **The knowledge pass (A5).** After the plan validates, the orchestrator adds one
   `extract_claims` task with `mode: conflicts` when `agent.yaml:knowledge.cross_source_pass` says
   to: `never`, `comparative` (the default: when the intent requires a comparison, the same test
   the reasoning engine uses for its two-sides rule), or `always`. It is not added when the plan
   already has a task that reads the knowledge base. It takes the next free task number, is
   recorded with `TASK_CREATED` (`origin: knowledge_pass`), and because it is added after
   validation, `plan_validity` still measures the planner alone.
2. **Building.** If any task in the graph routes to `KNOWLEDGE_GRAPH`, the run's knowledge base is
   extracted once, before execution, stored through `open_knowledge_base` (Neo4j or memory), put on
   `MissionResult.knowledge`, and announced with `KNOWLEDGE_EXTRACTED`. A plan that never asks for
   entities or claims costs no extraction calls.
3. **The tool.** `extract_entities` and `extract_claims` route to `KNOWLEDGE_GRAPH`, served only by
   `knowledge_graph`, so routing is deterministic. It reads the snapshot from `ToolContext` and
   returns each side of each conflict as its own item, on the cited line, naming the other side:

   ```
   finance.txt:r12  Project Aurora.completion_date = 14 May 2026
                    [conflicts with report.txt:r10 = 30 April 2026]
   ```

   `mode: all` adds the other grounded claims, capped at 30. Ungrounded claims are never returned.
   With no knowledge base the tool falls back to the regex extraction these task types used before,
   and says so.
4. **Reasoning is unchanged.** It still has to state the finding, and the binder, the comparative
   rule, the relevance gate and verification still judge it. The knowledge layer supplies the
   pairing. It does not supply the conclusion.
5. **Findings are recorded in the graph.** With the knowledge base in Neo4j, each finding becomes a
   `(:Finding)` node that `CITES` the claims and documents behind its resolved citations, which is
   what the 3D view lights up when a finding is clicked.

### Measured in a mission (Phase 30)

On this repository's 8 scenarios the knowledge pass changed no positive result. It costs about 13 s
per run and one task. **Member 3's conflict rule finds same-attribute contradictions** (two reports
giving one shipment two arrival dates), and **cannot express planned-vs-actual ones** ("approved
completion 30 April" vs "latest milestone 14 May", "approved budget" vs "total spend"). Those are
the kind the Aurora and Helix fixtures plant. Experiment 003 (preliminary) has the numbers. The
full comparison is on the shipment scenarios in Phase 34.
