# Evaluation

The measurement system. This is where the claim "the agent works" becomes a number that
something other than optimism produced.

Configuration lives in `.agent/config/evaluation.yaml`. The runner is
`backend/app/evaluation/` (Phase 20).

## The one rule

**No metric is ever hard-coded.** Every number in every report is computed by a scorer from
a real execution of a real run. A fabricated evaluation figure would invalidate the entire
project, because measurement is the only thing separating this from a demo that happened to
work once.

This is invariant #5, and the harness is built so that violating it requires deliberate
effort: scorers take runs as input, reports are generated files, and no report is ever
edited by hand.

## Layout

| Directory | Contents |
|---|---|
| `datasets/` | Scenario inputs used for measurement — ≥ 20 by Phase 20 |
| `expected_outputs/` | Ground truth: expected intents, DAG edge sets, findings |
| `scoring/` | One scorer per metric, each independently unit-tested |
| `reports/` | Generated reports, committed. These are the numbers we present. |

## Metrics

Defined and thresholded in `config/evaluation.yaml`:

| Metric | Measures |
|---|---|
| Intent accuracy | Did it understand what was asked? |
| Plan validity | Did it produce a legal, executable DAG? |
| Dependency correctness | Did it get the ordering right? |
| Tool selection accuracy | Did it pick the right capability? |
| Evidence coverage | Is every finding actually supported? |
| Verification success | How many candidate findings survive an independent check? |
| Replanning success | Can it close the gaps it finds? |
| Unsupported claim rate | How often does it assert something it cannot support? |
| Task efficiency | How much work did it waste? |
| Latency | How long did it take, per phase and overall? |

## Why "unsupported claim rate" is the headline metric

Every other metric can look good while the system is still failing at its purpose. A plan
can be valid, tools correctly chosen, tasks efficiently executed — and the report can still
assert things nothing supports. That single number is the closest thing to a direct measure
of whether the evidence-first architecture is doing its job.

It is the only metric with a `fail_build_above` threshold.

## Ground truth

`expected_outputs/` holds what a careful human analyst would conclude from each fixture set.
Findings are matched fuzzily at the claim level, because two correct phrasings of the same
contradiction are both correct. Dependency edges are matched exactly, because a DAG either
orders the work correctly or it does not.

Writing ground truth is slow and is the reason the dataset is 20 scenarios rather than 200.
A small, honest dataset beats a large, sloppy one.

## Reports

Generated to `reports/<timestamp>-<model>.json` plus a Markdown summary, stamped with the
model, prompt versions and config hash. `regression.py` compares against the last committed
report for the same suite and fails on degradation beyond tolerance — and also flags
unexplained *improvements*, since a metric that jumps without a cause usually means the
measurement broke.
