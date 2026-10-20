# Held-out scenarios (Phase B2)

Scenarios written by teammates who have **not** seen the prompts, the configuration or the
evaluation results, so that a change tuned on the main suites cannot be measured on the same data it
was tuned on. B8 (held-out tuning) keeps a change only if the held-out score improves.

## The protocol

1. A teammate writes the files and the scenario without reading `.agent/prompts/` or the reports.
2. Each scenario is a normal dataset file in `.agent/evals/datasets/` with `suites: [heldout]` and a
   `category` naming the kind of file it tests (`audio`, `video`, `scan`, `photo`, ...), plus an
   entry in `.agent/evals/benchmark/answers.yaml`.
3. Its files go in `.agent/fixtures/documents/`; a generator script beside them if they are made.
4. It is run with `python -m app.cli eval --suite heldout` and the report is committed as it came out.

## Status

None committed yet. The suite name is reserved and the runner already accepts it; the scenarios
have to come from the teammates, because a held-out scenario written by the person tuning the system
is not held out.
