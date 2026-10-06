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

## Phase 41 additions

**Fourteen scenarios.** Three Orion scenarios (suite `formats`) read through the Word, Excel, image
and subtitle parsers of Phases 38-39: `orion_ledger_overrun` (a Word memo's approved budget against an
Excel ledger's total), `orion_scanned_delivery` (the delivered quantity exists only in a scanned
note, so the finding exists only if OCR read it), and `orion_meeting_consistent` (a negative case:
subtitles and Word minutes that agree in different words). Fixtures are generated once by
`.agent/fixtures/make_orion_fixtures.py` and committed.

**Repeated runs.** `python -m app.cli eval --repeat 3` runs the suite three times. The last run is the
report (and the new baseline); every run and the spread (`*-all-x3.md`: mean, standard deviation and
range per metric, and whether each scenario reached the same verdict every time) go to
`reports/repeats/<stamp>/`. A metric whose range exceeds its regression tolerance is flagged: one
run of that metric cannot tell a regression from noise. Every run is held to the thresholds, in the
CLI and in CI.

**Retrieval (Experiment 006).** `python -m app.cli eval-retrieval` scores search, not the agent:
hit@1, hit@5, recall@5, MRR and passage hit@5 for lexical search, semantic search over two chunkers,
and a rank-fused hybrid, over `retrieval/queries.yaml` (keyword, paraphrase and unanswerable queries,
each with the exact lines a reader would cite). Embeddings only, about a minute. Reports in
`experiments/exp-006-retrieval/`; results and decisions in `.claude/architecture/retrieval.md`. CI
checks they parse and that none was made with the echo provider.

## Reports

Generated to `reports/<timestamp>-<model>.json` plus a Markdown summary, stamped with the
model, prompt versions and config hash. `regression.py` compares against the last committed
report for the same suite and fails on degradation beyond tolerance — and also flags
unexplained *improvements*, since a metric that jumps without a cause usually means the
measurement broke.
