# Experiment Log

This is an AI systems project, so model- and prompt-level experiments are recorded with the
same rigour as code changes. Every entry states its objective, setup, dataset, metrics,
result and the decision it drove.

Experiments run against the evaluation harness (Phase 20), on pinned scenarios with a pinned
prompt version, so results are comparable across entries.

---

## Planned

### Experiment 001 — Planner performance across local models

**Blocked until:** Phase 20 (evaluation harness)
**Objective:** Determine which local model to default to for planning.
**Models:** `qwen3:4b` (current default) vs. a larger model (`qwen3:8b` or `llama3.1:8b`)
**Dataset:** 20 investigation scenarios from `.agent/evals/datasets/`
**Metrics:** plan validity, dependency correctness, tool selection accuracy, structured-output
repair count, latency per run.

The repair count matters as much as the accuracy here: a model that needs two repair passes
per call is a different engineering proposition from one that needs none, even at equal
final accuracy.

### Experiment 002 — Cost-aware action selection vs. naive selection

**Blocked until:** Phase 17
**Objective:** Measure whether the planning policy reduces work without reducing resolution.
**Setup:** Same scenarios, `PLANNING_POLICY=heuristic` vs. `PLANNING_POLICY=naive`
**Metrics:** tasks executed per resolved finding, total tool calls, evidence coverage,
replanning success rate, wall-clock.

**Prediction to be tested:** the heuristic policy reduces executed tasks per resolved finding
without lowering evidence coverage. If coverage drops, the policy is trading correctness for
cost and the scoring weights are wrong.

---

## Completed

### Experiment 005 — Knowledge extraction on Member 3's own sample (Phase 28 acceptance)

*Numbered 005 because 003 (knowledge pass on/off) and 004 (`baseline` vs `composite` verifier) are
reserved by the integration plan for Phase 34.*

**Date:** 2026-10-03. **Model:** `qwen3:4b` via Ollama. **Prompt:** `knowledge` v1.
**Input:** the 7 chunks of Member 3's `sample_data.json` (archived in
`integrations/originals/member-3/`), one document each. **Question:** does the ported extractor
find what Member 3's demo was built to find: Shipment 4821 arriving on 14 September in one report
and 16 September in another?

**Run 1** (entity grounding not yet applied)

- 46.6 s, 7 model calls, 0 failed chunks, 16 claims, 0 ungrounded claims, 3 relationships skipped
- **Found:** `Shipment 4821 / arrival_date`: `14 September` (`shipping_report_a.txt:r1`) vs
  `16 September` (`shipping_report_b.txt:r1`), kind `DATE`
- Also: `received_by`: `Rahul Sharma` vs `security logs`. **A misread.** Report B says the
  arrival came "according to security logs", and the model read that as the receiver. The value
  is on the line, so grounding cannot catch it
- Also: `was_present_at`: `Arjun Verma` vs `Rahul Sharma`, both from the witness statement. That
  is the discrepancy Member 3 planted, under a poor attribute name
- **Defects seen:** an entity "Shipment 482:1", which appears in no text, and the same claim
  stored twice from one line

**Fixes from run 1:** entity names are grounded like claim values (a name on no line of its chunk
is counted as `entities_ungrounded` and not created), and identical claims are stored once.

**Run 2**

- 40.5 s, 7 calls, 0 failed, 17 claims, 0 ungrounded claims, 6 entity names dropped as ungrounded
- **Found:** the same arrival-date conflict, both sources
- The witness discrepancy now comes out as `Mumbai warehouse / manager_on_duty`: `Arjun Verma` vs
  `Rahul Sharma`
- The `received_by` misread persists, now as `Rahul Sharma` vs `Mumbai facility`
- **The six dropped names were checked one by one.** One was the mangled "Shipment 482:1". The
  other five were **names the model echoed from the known-entities list** (feature A8) into chunks
  that never mention them, such as "Rahul Sharma" in shipping report B. Grounding is what makes
  A8 safe to use
- `investigate("Shipment 4821")`: 3 source documents, 4 claims, 2 conflicts, network of 2
- Timeline: 14 Sep (arrival A), 14 Sep (`SAME_TIME_AS`), 16 Sep (`AFTER`), 20 Sep
- Search "Rahul warehouse": top hit `present_at = Mumbai warehouse`, score 5, with reasons
  "direct entity match, keyword match: warehouse, has source document"

**Conclusion.** The acceptance criterion holds: the planted contradiction is found, with both
citations, on both runs. The knowledge layer is no better than its extraction, though. One false
conflict per run came from a misread the grounding check cannot see. Its conflicts are therefore
inputs to reasoning and verification (Phase 30), never findings by themselves.

**Addendum (Phase 29).** Run 3, stored through `open_knowledge_base` into Neo4j as
`run_00000000a3a3`: entities, claims, conflicts, timeline, search ("Rahul warehouse") and
`investigate("Shipment 4821")` all compared equal between the Neo4j store and the in-memory store.
Neo4j held 1 run, 6 documents, 14 entities, 16 claims, 3 conflicts and 3 `CONFLICTS_WITH` edges.
The arrival-date conflict was found again, so it held across three runs.

### Experiment 003 (preliminary, Phase 30) — the knowledge pass, off vs on

**Date:** 2026-10-03/04. **Model:** `qwen3:4b`. The full 8-scenario suite twice, back to back in one
model session (BUG-019: output differs between sessions), with `knowledge.cross_source_pass`
`never` and then `comparative`. Run before and after BUG-020.

**Before BUG-020** (the PDF fix):

| | `never` | `comparative` |
|---|---|---|
| `aurora_contradiction` | 1, passes | 1, passes |
| `aurora_pdf_timeline` | 0, fails | 0, fails |
| `aurora_no_contradiction` (negative) | 1 invented | 1 invented, a different one |
| latency | 15.6 s | 28.5 s |

**After BUG-020** (`comparative` is baseline `20261004T172506`):

| | `never` | `comparative` |
|---|---|---|
| `aurora_contradiction` | 2, passes | 2, passes |
| `aurora_pdf_timeline` | **2, passes** | **2, passes** |
| `aurora_no_contradiction` (negative) | 1 invented | 1 invented, a different one |
| `helix_evidence_gap` | 0 | 1 |
| task_efficiency | 1.447 | 1.654 |
| latency | 25.0 s | 37.9 s |

**Why the pass did not move anything here.** On `aurora_contradiction` the knowledge layer extracted
31 claims and paired **no** conflicts. Both of Aurora's planted contradictions compare *different*
attributes: "approved baseline completion 30 April" against "latest completion milestone 14 May"
(planned vs actual), and "total spend 450,000" against "approved budget 380,000" (spend vs budget).
Member 3's rule flags the **same** attribute with different values, which is what his shipment
sample contains, and it cannot express a planned-vs-actual contradiction by design. Reasoning found
both contradictions itself once it could read the evidence (BUG-015, BUG-020).

**Chunk size was tried and rejected.** On the two Aurora text documents: 3000 chars gave 23.8 s, 6
relevant claims, 0 ungrounded; 600 chars gave 36.4 s, 8 claims, 3 ungrounded; 300 chars gave 66.4 s,
22 claims, 8 ungrounded, and nonsense such as `approved_budget = Q2 2026`. 3000 stays.

**Decision.** `cross_source_pass` stays `comparative` for now: it is what gives comparative missions a
knowledge graph for the Phase 31-32 API and 3D view. The decision on recall is deferred to the full
Experiment 003 in Phase 34, on the shipment scenarios, whose contradictions are same-attribute.
The cost is stated: about +13 s per run and one task.
