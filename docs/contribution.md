# Contribution statement — Member 1: Intelligence & Agents

**Scope:** understanding user intent, planning tasks, selecting tools, and reasoning across all
gathered information.
**Repository:** [github.com/24markjr/M2LLM](https://github.com/24markjr/M2LLM)
**Baseline for every number below:** `.agent/evals/reports/20260925T104354-qwen3-4b-all.json`
(`qwen3:4b`, prompt versions `intent=2 planner=2 reasoning=2 relevance=2 verification=1`)

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
| **Intent understanding** — objective → goal + required operations from a closed vocabulary, or a refusal to plan | [`intelligence/intent/engine.py`](../backend/app/intelligence/intent/engine.py) | `intent_accuracy` **0.574** |
| **Task planning** — a validated DAG, with deterministic repair and bounded re-prompting | [`intelligence/planner/`](../backend/app/intelligence/planner/) | `plan_validity` **0.333**, `dependency_correctness` **0.833** |
| **Tool selection** — capability filter → schema compatibility → model tiebreak only on a tie | [`intelligence/router/engine.py`](../backend/app/intelligence/router/engine.py) | `tool_selection_accuracy` **1.000** |
| **Reasoning over evidence** — claims bound to real locators, classification and confidence recomputed | [`intelligence/reasoning/engine.py`](../backend/app/intelligence/reasoning/engine.py) | `evidence_coverage` **1.000**, `unsupported_claim_rate` **0.000** |
| **Evidence gap detection** — deterministic, naming the specific absent element | [`intelligence/evidence_gap/detector.py`](../backend/app/intelligence/evidence_gap/detector.py) | `replanning_success` **0.658** |
| **Adaptive replanning** — the graph is edited while it runs, bounded, every stop reasoned | [`intelligence/replanning/controller.py`](../backend/app/intelligence/replanning/controller.py) | `task_efficiency` **2.306** |
| **Measurement** — ten metrics computed from real runs | [`app/evaluation/`](../backend/app/evaluation/) | reports in [`.agent/evals/reports/`](../.agent/evals/reports/) |

Supporting: concurrent execution by dependency wave, an append-only event log from which a run is
fully reconstructable, a FastAPI + SSE surface, and a React operations console that streams a run
live and can replay a recorded one.

**581 tests**, `mypy --strict` clean across 83 modules, 82% coverage (90–100% on
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

## The open defect

The negative scenario currently produces **3 findings where none is correct.** They are
restatements of the source — true, correctly cited, and not answers to the question asked.

CI is red on `main` because of it, and I have not weakened the threshold to change that. It is
BUG-005, it is on the evaluation dashboard, and it is the highest-value remaining work. I would
rather present a red build with a known cause than a green one that got there by lowering a bar.

Also honestly outstanding: three evaluation scenarios where the plan calls for twenty; the API does
not yet persist runs; the CLI still holds a second copy of the pipeline that should collapse onto
the orchestrator; no frontend test runner.

---

## Boundaries respected

Members 2, 3 and 4 own context retrieval, knowledge search and verification. Each is reached
through a `Protocol` selected by environment variable, each has a local fallback so this side was
never blocked by another timeline, and **no member's implementation is imported directly** — a test
parses the source tree to prove it. The same test proves invariant 1: the language model is
reachable from exactly one package,
[`app/llm/`](../backend/app/llm/).

---

## How to check any of this in five minutes

```bash
python -m app.cli health                      # the engine answers
pytest tests -m "not llm"                     # 581 tests, no model needed, ~18s
pytest tests/unit/test_llm_isolation.py -v    # invariant 1, proven by parsing the source
pytest tests/unit/test_invariants.py -v       # the whole "must not do" list
pytest tests/unit/test_adversarial.py -v      # injection, corrupt input, zero-finding runs
python -m app.cli eval --suite all            # regenerate every number in this document
```

The last command is the one that matters. **No metric in this repository is hand-written** — each
report carries its model, prompt versions and config hash, and two reports with different stamps
are refused as incomparable rather than quietly compared.
