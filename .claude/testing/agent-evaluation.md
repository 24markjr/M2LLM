# Agent evaluation

**Phase:** 20
**Code:** `backend/app/evaluation/` — `runner.py`, `metrics.py`, `report.py`
**Datasets:** `.agent/evals/datasets/*.yaml`
**Reports:** `.agent/evals/reports/<timestamp>-<model>-<suite>.{json,md}`

```bash
python -m app.cli eval --suite all       # writes a timestamped report
python -m app.cli eval --suite core --no-write
```

The point of this harness is that claims about the agent become **measured**, not asserted.
Every figure in a report is computed from a real run. No value is written by hand, and a number
that did not come out of a run cannot appear in one.

---

## It has already earned its keep

The first run measured three defects nobody had predicted:

| Finding | What it meant |
|---|---|
| `plan_validity` 0.333 | two plans in three needed repair before they could execute |
| `task_efficiency` 3.639 | plans were 3.6x the minimum size |
| `aurora_no_contradiction` produced 8 findings | **the agent confabulated**, and 0 is the correct answer |

The third is the one that matters most, and it is the one no positive scenario could ever have
found. It led to the relevance gate (`.claude/architecture/reasoning-engine.md`), and tracing it
uncovered a chain of four further defects — including input and output token budgets being the
same number.

---

## The ten metrics

| Metric | Definition | Direction |
|---|---|---|
| `intent_accuracy` | operation-set F1 against the expected intent | higher |
| `plan_validity` | share of plans passing the validator with **zero repairs** | higher |
| `dependency_correctness` | edge-level precision/recall against the expected DAG | higher |
| `tool_selection_accuracy` | share of tasks routed to the expected tool | higher |
| `evidence_coverage` | share of findings with at least one resolved evidence ref | higher |
| `verification_success` | share of candidate findings surviving verification | higher |
| `replanning_success` | share of detected gaps closed within the iteration ceiling | higher |
| `unsupported_claim_rate` | share of claims no resolved evidence supports | **lower** |
| `task_efficiency` | executed tasks ÷ minimal sufficient tasks | **lower** |
| `latency_s` | wall-clock per run | **lower** |

`unsupported_claim_rate` is the hallucination proxy and the only metric that **fails the build
outright**, above 0.15.

Two metrics are easy to misread:

- **`verification_success` should not be near 1.0.** A verifier that approves everything scores
  perfectly and is worthless. A suspiciously high value is a reason to inspect the verifier.
- **`evidence_coverage` returns 1.0 when there are no findings.** An empty result cannot be
  scored as poor coverage, because a correct empty result exists. This is exactly why the
  negative-case check below is needed as well.

---

## The two checks no metric can express

### Negative cases — finding something that is not there

A scenario with `expect_zero_findings: true` has no answer to find. Producing findings on it is
the failure.

**No metric can catch this.** An agent that invents findings on a negative case scores 1.0 on
coverage, 1.0 on verification and 0.0 on unsupported claims — a perfect score for being exactly
wrong. So it is checked separately, and it fails the build.

The report records the **claims**, not just a count. A count says the agent confabulated; it
does not say what it confabulated, and the difference is the difference between a number that
moves and a defect anyone can act on.

### Positive cases — finding nothing that is there

The mirror, and it was missing until the relevance gate briefly suppressed every finding on
`aurora_contradiction` and the suite still printed `THRESHOLDS: passed`. An agent reporting
nothing scores 1.0 on coverage, 1.0 on verification and 0.0 on unsupported claims — the same
perfect score, for the opposite failure.

A scenario declaring `expected_claims` that produces **zero** findings is now a build failure
(`EvalReport.blind_spots`).

Both checks exist because the ten metrics measure *how well the agent did the work*, and these
two ask *whether the work should have been done at all*.

---

## Datasets

```yaml
id: aurora_contradiction
suites: [core, all]
objective: >
  Investigate the Aurora project reports and identify any contradictions between the
  timeline and the financial information.
documents: [aurora_project_report.txt, aurora_financial_report.txt, aurora_budget.csv]

expected_operations: [extract_timeline, extract_budget, compare_sources, ...]
min_tasks: 6
minimal_tasks: 8                    # the denominator of task_efficiency
expected_edges: [[extract_timeline, compare_sources], ...]
expected_tools: {extract_timeline: document_extract}
expected_claims: ["2026"]           # substring match
```

`expected_claims` is matched on **substring, not equality**. Two correct phrasings of the same
contradiction are both correct, and demanding exact wording would measure the model's prose
style rather than whether it found the thing.

Current suites: `core`, `negative`, `all`. Three scenarios exist
(`aurora_contradiction`, `aurora_timeline_only`, `aurora_no_contradiction`). The plan calls for
≥ 20 — see *Known gaps*.

---

## Reports carry a stamp

```
model        : qwen3:4b
config       : sha256:69b516212335b48e
prompts      : {'intent': 2, 'planner': 2, 'reasoning': 2, 'relevance': 2, 'verification': 1}
```

Two numbers produced by different models, or different prompt versions, are **not comparable**.
Comparing them quietly would turn a model swap into an apparent regression, or hide a real one
behind an upgrade. `comparable_key` is model + prompt versions + config hash, and the regression
check refuses to compare across a change in any of them. See
`.claude/testing/regression-testing.md`.

Reports are generated files. Nothing in `.agent/evals/reports/` is written by hand.

---

## Known gaps

- **Three scenarios, not twenty.** The three in place cover the contradiction case, a
  single-document case and the negative case — enough for the metrics to be real, not enough to
  be a benchmark. Tool failure, multi-document and evidence-gap scenarios are the next to add.
- **Not re-run since the intent, plan-cap and observation-budget fixes.** The last committed
  report predates them, so its numbers are stale and the regression check will correctly refuse
  to compare against it (prompt versions changed).
- **Experiment 001 is unrun.** `.claude/logs/experiment-log.md` has it specified and blocked on
  this harness, which now exists.
