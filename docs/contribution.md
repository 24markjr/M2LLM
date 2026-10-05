# Contribution statement — Member 1: Intelligence & Agents

**Scope:** understanding user intent, planning tasks, selecting tools, and reasoning across all
gathered information.
**Repository:** [github.com/24markjr/M2LLM](https://github.com/24markjr/M2LLM)
**Baseline for every number below:** `.agent/evals/reports/20261005T050619-qwen3-4b-all.json` (11 scenarios)
(`qwen3:4b`, prompt versions `intent=2 planner=2 knowledge=1 reasoning=5 relevance=3 verification=2`,
`composite` verifier)

---

## The claim

An agent that decides *what work to do*, does it, and then reports only what the evidence
supports — where "what the evidence supports" is computed, not asserted.

The distinguishing decision is one line of enforcement:

```python
Confidence(value=0.96)   # ValidationError
```

There is no constructor in this system that takes a bare confidence number.
[`app/schemas/finding.py`](../backend/app/schemas/finding.py) admits only
`Confidence.compute(...)`, which derives a value from four recorded factors: how many citations
resolved, how much independent evidence supports the claim, whether the sources agree, and the
ceiling its classification imposes. Because it is enforced in the type rather than by convention,
**no code path anywhere can assert a confidence it did not derive** —
[`tests/unit/test_invariants.py`](../backend/tests/unit/test_invariants.py) proves it.

Everything else in the design follows from taking that seriously.

---

## What was built, and where it is

| Capability | Where | Evidence it works |
|---|---|---|
| **Intent understanding** — objective → goal + required operations from a closed vocabulary, or a refusal to plan | [`intelligence/intent/engine.py`](../backend/app/intelligence/intent/engine.py) | `intent_accuracy` **0.595** |
| **Task planning** — a validated DAG, with deterministic repair and bounded re-prompting | [`intelligence/planner/`](../backend/app/intelligence/planner/) | `plan_validity` **0.636**, `dependency_correctness` **0.844** |
| **Tool selection** — capability filter → schema compatibility → model tiebreak only on a tie | [`intelligence/router/engine.py`](../backend/app/intelligence/router/engine.py) | `tool_selection_accuracy` **1.000** |
| **Reasoning over evidence** — claims bound to real locators, classification and confidence recomputed | [`intelligence/reasoning/engine.py`](../backend/app/intelligence/reasoning/engine.py) | `evidence_coverage` **1.000**, `unsupported_claim_rate` **0.000** |
| **Evidence gap detection** — deterministic, naming the specific absent element | [`intelligence/evidence_gap/detector.py`](../backend/app/intelligence/evidence_gap/detector.py) | `replanning_success` **1.000** (vacuous: no gaps on this baseline) |
| **Adaptive replanning** — the graph is edited while it runs, bounded, every stop reasoned | [`intelligence/replanning/controller.py`](../backend/app/intelligence/replanning/controller.py) | `task_efficiency` **1.650** |
| **Measurement** — ten metrics computed from real runs | [`app/evaluation/`](../backend/app/evaluation/) | reports in [`.agent/evals/reports/`](../.agent/evals/reports/) |

Supporting: concurrent execution by dependency wave, an append-only event log from which a run is
fully reconstructable, a FastAPI + SSE surface, and a React operations console that streams a run
live and can replay a recorded one.

**925 tests**, `mypy --strict` clean across 116 modules, 89% coverage (90–100% on
`intelligence/**` and `schemas/**`).

---

## Four design decisions I would defend

**1. Deterministic first, model only where judgement is genuinely needed.**
Tool routing filters by capability and schema compatibility and asks a model *only* to break a
remaining tie. Gap detection decides that a gap exists by comparing claim elements against resolved
evidence — no model involved; a model is asked only to phrase a query for a gap that already
exists. A model that could decide whether a gap exists could also decide there wasn't one.

**2. Verification is outside the plan and cannot see the reasoning it checks.**
[`.claude/architecture/verification.md`](../.claude/architecture/verification.md). A check that
shares the reasoning it is checking is not independent. When the external verifier is unreachable
the system falls back to a weaker local one and **marks the finding `degraded`** — surfaced in the
API, the report and the UI. A check that quietly got weaker is worse than no check, because no
check is visible.

**3. An unresolvable citation is kept, not dropped.**
Dropping it would leave a claim that looks fully supported. Keeping it as `UNRESOLVED` caps the
confidence, changes the classification, and appears in the report. This is the opposite of what a
system optimising for looking good would do.

**4. An empty result is a correct answer.**
Asked whether a consistent document contradicts itself, the right output is nothing. The evaluation
suite has a negative scenario for exactly this and **fails the build** when the agent finds
something.

---

## What the measurement found that I would not have

The evaluation harness is the part I would point a reviewer at first, because it found real defects
rather than confirming what I already believed. Its first run produced three:

<!-- historical -->

| Measured | Meaning | Outcome |
|---|---|---|
| 8 findings on a zero-finding scenario | **the agent confabulated** | led to the relevance gate |
| `task_efficiency` 3.639 | plans 3.6× minimal | one replan iteration had inserted 24 tasks |
| `plan_validity` 0.333 | 2 plans in 3 needed repair | prompt v2 |

<!-- /historical -->

Tracing the first uncovered a chain of four further defects, each hiding the next — recorded as
BUG-004 to BUG-011 in [`.claude/logs/bug-log.md`](../.claude/logs/bug-log.md). The one I would
highlight: **an input and an output token budget were the same number.** Reasoning bounded its
observations by `max_tokens`, which caps what the model may *generate*, so evidence was compressed
five times more than intended — and summarising is precisely what removes the dates and figures a
contradiction rests on. A scenario with two planted contradictions returned nothing.

Fixing that chain, measured on the same objective and model: tasks planned 16 → 7, findings 0 → 4
(3 verified), latency 91.8 s → 45.2 s.

Two of those five defects existed because a field was *defined but never set*
(`RequiredOperation.optional`) or *scoped wrongly* (`_TOLERANCES` below the `__main__` guard, so
the regression check never ran). Neither was visible from reading the code. Both were visible in a
number.

---

## The open defect, and what fixing it revealed

The negative scenario produced **3 findings where none is correct** — restatements of the source,
true and correctly cited and not answers. That is fixed: it now produces none,
`unsupported_claim_rate` is 0.000 and `evidence_coverage` is 1.000.

The fix is the part I would want discussed. Asking a model more firmly not to do it did not work,
and tuning the relevance gate traded one failure for the other — kept loosely it admitted
restatements, kept tightly it suppressed real contradictions. One model judgement cannot hold both
ends of that. So the decision became structural: **a claim of conflict must cite both sides**, and
a claim fully supported by a single locator cannot answer a comparative objective. It reads the
intent rather than the claim, because the same sentence is an answer to "extract the timeline" and
noise in "do these conflict?".

**What it revealed is less comfortable.** That scenario previously reported four findings; three
were restatements, and every metric counted them as successes. Removing them did not lower the
agent's recall — it exposed it. The real figure was always about one genuine contradiction per run,
and the ceiling is the model: `qwen3:4b` does not reliably produce a claim that pairs two
documents.

A second negative case, added later over a CSV rather than prose, then caught a contradiction
between two of my own prompts: the relevance prompt invited claims that state a negative
conclusion, and the agent duly reported "the budget file does not contradict itself". True, and not
a finding — absence cannot be cited, so nothing can support it. Both prompts now say so, and both
negative cases produce nothing.

For weeks after that the build stayed red, first on positive scenarios that found nothing, then on
a negative case that invented a finding again with no code change (BUG-019): the model's output is
stable within a session and differs between them. I did not weaken the threshold. The fix, on
2026-10-05, was structural again and narrow: the invented conflict stated a value ("31 January
2026") that neither of its cited lines contains, so a claim of conflict must now have **both of its
values in the lines it cites**, not only cite both sides. Measured on the full suite, the negative
case produces nothing, every positive scenario keeps its findings, and every threshold passes.

Honestly outstanding: eleven evaluation scenarios where the plan called for twenty; one run per
experiment arm, on a model whose output varies between sessions; the 3D graph is not rebuilt in
replay; facts in memory merge only when the model names an attribute the same way twice.

---

## Members 3 and 4: what they built, and what it became

Members 3 and 4 built their parts as standalone prototypes. Their features were ported into this
codebase with the same logic ([ADR-009](../.claude/decisions/ADR-009-port-teammates-in-process.md));
**the design and the logic below are theirs**, and what the port changed is listed beside each. The
full inventory, original file by original file, is
[`teammate-port.md`](../.claude/integrations/teammate-port.md); the originals are archived in
[`.claude/integrations/originals/`](../.claude/integrations/originals/).

**Member 3 — the knowledge graph** (`jarvis-member3/`)

| Their feature | Where it lives now | What the port changed |
|---|---|---|
| LLM extraction of entities, relationships and claims (`extractor.py`) | `intelligence/knowledge/extraction.py` | Values and names grounded on their source line; CSV extracted without a model; names carried across chunks |
| Entity resolution and relationship linking (`resolve.py`, `db.py`) | `intelligence/knowledge/store.py` | Per run instead of one global store; wider name normalisation |
| Contradiction detection by entity and attribute (`contradictions.py`) | `intelligence/knowledge/conflicts.py` | Values compared by kind (date, number, text); grounded claims only |
| Timeline with before/after/same, and claim comparison (`timeline.py`) | `intelligence/knowledge/timeline.py` | No invented year; differing precision is "unknown" |
| Knowledge graph and N-hop neighbourhood (`graph.py`) | `intelligence/knowledge/graph.py`, Neo4j store | Neo4j or in memory, one test suite for both |
| Hybrid search with explainable score (`retrieval.py`) | `intelligence/knowledge/search.py` | Same score and reasons |
| The 14-endpoint API (`main.py`) | `api/v1/knowledge.py` | Per mission, typed errors, CORS on the allow-list |
| The dashboard (`dashboard.html`) | Mission Control, `components/graph3d/` | Interactive 3D (2D fallback): sub-nodes, highlight, hover, evidence trail |
| Sample data (`sample_data.json`) | `.agent/fixtures/documents/shipment_*.txt` | Verbatim; now three evaluation scenarios |

Measured: their planted contradiction (Shipment 4821, 14 vs 16 September) is found by the full agent
with their knowledge pass on and missed without it (Experiment 003).

**Member 4 — trust, security, memory, evaluation** (`mem4/MajorP/Mem-4/`)

| Their feature | Where it lives now | What the port changed |
|---|---|---|
| TF-IDF relevance and claim verification, four statuses (`trust/verifier.py`) | `intelligence/trust/tfidf.py`, `lexical.py` | Matches scikit-learn to 4.4e-16 with no dependency; dates conflict too |
| Entity-aware conflict rule | `intelligence/trust/lexical.py` | Adds disjoint dates; times by minute |
| Answer-level hallucination evaluation (`hallucination_evaluator.py`) | `intelligence/trust/answer.py` | Logic unchanged |
| Prompt-injection scanner, 21 patterns and severity (`security/injection_guard.py`) | `security/injection.py` | Patterns verbatim; run on every document; a flag never drops evidence |
| Safe prompt construction | `security/injection.py:wrap_untrusted` | The wrapper escapes its own closing tag |
| 14-case security suite | `.agent/evals/security/injection_cases.yaml` | Their 14 verbatim plus 13; 27/27 |
| Working, episodic and semantic memory (`memory/`) | `app/memory/` | Derived from finished runs; facts only from verified findings, with support instead of `confidence=1.0`; never read back into a run |
| Synthetic benchmark generator and runner (`eval/`) | `evaluation/trust.py`, `cli eval-trust` | Byte-identical data from seed 42; a stamped report CI re-runs |

Measured: their verifier, inside the `composite` verifier, is now the default. It rejected the one
invented finding the previous default passed, and nothing correct (Experiment 004).

---

## Boundaries respected

Member 2 owns context retrieval, reached through a `Protocol` with a local fallback so this side was
never blocked by another timeline. Members 3 and 4's work was **ported, not imported**: no teammate's
code is imported anywhere, and the ported features sit behind the same seams (the `KnowledgeBase`
protocol, the `VerificationProvider` seam). A test parses the source tree to prove it. The same test proves invariant 1: the language model is
reachable from exactly one package,
[`app/llm/`](../backend/app/llm/).

---

## How to check any of this in five minutes

```bash
python -m app.cli health                      # the engine answers
pytest tests -m "not llm"                     # 925 tests, no model needed, ~30s
python -m app.cli eval-trust --no-write       # Member 4's benchmark: 60/60, injection 27/27
pytest tests/unit/test_llm_isolation.py -v    # invariant 1, proven by parsing the source
pytest tests/unit/test_invariants.py -v       # the whole "must not do" list
pytest tests/unit/test_adversarial.py -v      # injection, corrupt input, zero-finding runs
python -m app.cli eval --suite all            # regenerate every number in this document
```

The last command is the one that matters. **No metric in this repository is hand-written** — each
report carries its model, prompt versions and config hash, and two reports with different stamps
are refused as incomparable rather than quietly compared.
