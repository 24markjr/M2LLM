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

*(none yet — the harness lands in Phase 20)*
