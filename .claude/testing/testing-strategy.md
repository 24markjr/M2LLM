# Testing strategy

**Phase:** 23
**CI:** [`.github/workflows/ci.yml`](../../.github/workflows/ci.yml)

```bash
cd backend
pytest tests -m "not llm"                    # the whole suite, no model needed
pytest tests/unit -q --cov=app               # with coverage
pytest tests/integration -p no:randomly      # needs Postgres
pytest -m llm                                # needs Ollama; excluded from CI
python scripts/check_eval_reports.py         # the committed baselines
```

---

## The one idea

**An agent cannot be tested only by checking that it produces output.** The failure modes that
matter here are all *quiet*: an investigation that reported findings it could not support, obeyed
an instruction hidden in a document, examined three documents out of five, or found something in a
corpus where there was nothing to find. Every one of those produces a run that looks successful.

So the suite is organised around what must **not** happen, not only around what should.

| Layer | What it proves | Model |
|---|---|---|
| Unit | each component behaves | `EchoProvider` |
| Invariants | the "must not do" list is enforced, not just written down | none — reads source |
| Adversarial | hostile, broken and empty input fails visibly | `EchoProvider` |
| Integration | persistence works against real Postgres | `EchoProvider` |
| Evaluation | the agent is measured, on a dataset in the repo | **real model, locally** |

The last row is the only one that needs a real model, and it is the only one CI cannot run.

---

## Determinism, and why the echo provider exists

Every test except the evaluation suite uses `EchoProvider`, which returns queued fixtures and
raises `NoFixtureError` when it has none.

That last behaviour is the important one. A provider that *invented* a plausible response when it
ran out of fixtures would let a test pass while exercising nothing, and the failure would be
invisible. Running out of fixtures is a loud error on purpose.

`LLM_PROVIDER=echo` is set for the whole CI workflow. A test that silently fell back to Ollama in
CI would hang rather than fail, which is the worst of both.

## `pytest-randomly`

Test order is randomised on every run and the seed is printed. A suite that only passes in one
order has tests leaking state into each other, and that leak is a bug that will eventually appear
as a mystery failure in something unrelated.

Two places opt out, and both say why: the integration suite (`-p no:randomly`) because schema
setup is ordered, and nothing else.

---

## Invariant tests — the "must not do" list

`tests/unit/test_llm_isolation.py` and `tests/unit/test_invariants.py`. These are the tests that
make the specification's rules checkable rather than rhetorical.

| Rule | How it is enforced |
|---|---|
| **Invariant 1** — the LLM is reached only through `app/llm/` | the source tree is parsed; an `httpx`/`ollama`/`openai` import outside `app/llm/` and `app/integrations/` fails |
| No `eval`, `exec`, or dynamic code execution | AST walk over every module |
| No environment access outside `app/core/config.py` | AST walk |
| Schemas import nothing from the application | AST walk — keeps the type layer a leaf |
| **Invariant 3** — no model deliberation is persisted | `REDACTED_PAYLOAD_KEYS` applied on the bus before any sink; the Ollama provider's source is checked for any read of `thinking` |
| **Invariant 7** — every loop is bounded | every ceiling asserted present and finite; `while True` occurrences are enumerated, and a new one fails until its exit condition has been read and recorded |
| Confidence is computed, never asserted | `Confidence(value=0.96)` must raise |
| Policy cannot exceed an `.env` ceiling | `clamp()`, plus realised bounds checked against settings |
| Closed vocabularies stay closed | member counts pinned; values must equal names; no duplicates |

Two of these are worth singling out.

**The `while True` test is a ratchet, not a ban.** It holds a list of the loops that exist, each
with its exit condition recorded and the date it was read. A new one fails the build until someone
writes down why it terminates. The point is to force the question, not to forbid the construct.

**The vocabulary counts are meant to fail.** Adding an `Operation` should break that test. A new
operation needs a task type that can execute it and a tool that can serve it, or planning produces
work routing cannot fulfil — and the failing test is the reminder to check that chain.

---

## The adversarial suite

`tests/unit/test_adversarial.py`.

**Prompt injection.** Two tests, and the second is the real one. The first asserts the framing is
actually present in the prompt when an observation contains an attack — it cannot assert the model
resisted, because that is a property of the model. The second assumes the injection *worked
completely* and shows it still cannot manufacture a citation: an invented locator resolves to
`UNRESOLVED`, which caps confidence and marks the finding. The defence is structural, not textual.

**Malformed plans.** Cycles rejected, dangling edges dropped, oversized plans truncated, uncovered
operations rejected. Self-dependency is rejected by the `Task` schema itself, which is stronger
than repairing it — a task of that shape cannot be constructed, so no engine has to cope with one.

**Empty and corrupt documents.** An unreadable file is excluded and reported, never treated as
empty. A file read as empty is what makes a partial investigation look complete.

**Zero-finding runs.** An honest empty result must stay empty, and a structured-output failure
must not become an invented finding. This is not hypothetical: the evaluation harness measured the
agent producing eight findings on a scenario with nothing to find.

**Tool failure storms.** Every tool raising must still terminate, mark the graph, and emit
`TASK_FAILED`; a downstream task whose inputs never arrived must not run and report success.

---

## CI

Cheapest check that can fail runs first: `lint` → `types` → `unit` / `integration` / `contract` /
`frontend` in parallel → `eval-regression`.

Three jobs deserve a note.

**`integration` fails if the database tests skip.** They skip themselves when no database is
reachable, which is right locally and wrong in CI — a silently-skipped integration suite is a
green tick over nothing.

**`contract` runs `export_openapi.py --check`.** The frontend's types come from
`docs/openapi.json`, so a stale one means the UI is built against a contract the API no longer
serves.

**`eval-regression` does not run the agent.** It cannot: that needs a local model. It validates
the committed reports and enforces the thresholds they recorded. **A green CI must not be read as
evidence the agent was measured** — the metrics are produced locally and committed, and that is
stated in the job's own comments so nobody infers otherwise.

Thresholds are enforced on the newest report per suite — the baseline — and deliberately not on
older ones. A report recording a defect that was later fixed is exactly the evidence worth
keeping, and a gate that failed on it would pressure someone into deleting the record to go green.

### Coverage

Measured 82% overall; `app/intelligence/**` and `app/schemas/**` sit at 90–100%, which meets the
Phase 23 target of ≥ 80%.

The CI floor is set at **75%**, below the current figure on purpose. A threshold equal to today's
coverage turns every unrelated change into a coverage failure, and a team that fights the gate
starts deleting tests to satisfy it.

---

## Current state, stated plainly

**CI runs on every push to `main` and on every pull request.** As of 2026-09-25 it has run six
times. Six of the seven jobs pass - lint, types, frontend build, OpenAPI freshness, and the
integration suite against a real Postgres service, all green on their first attempt. The build is
red because `eval-regression` fails on the evaluation baseline's positive-case blind spot, which is
that job doing its job.

**The first run failed for a reason no local check could have caught, and it was the workflow's
fault.** The workflow sets `LLM_PROVIDER=echo` for every job, so nothing can reach a real model by
accident. `test_defaults_are_usable_without_an_env_file` asserts the default provider is `ollama`,
and `Settings(_env_file=None)` disables the `.env` *file* but still reads the real environment - so
the job's own variable overrode the default the test existed to check.

The test was not hermetic, and any developer with `LLM_PROVIDER` exported in their shell would have
hit the same thing. It now clears every variable `Settings` reads, derived from the model's own
fields so a setting added later cannot be forgotten. The workflow keeps the variable: preventing an
accidental model call in CI is worth more than the one test it exposed.

**The remaining failure is the gate working.**

The evaluation baseline (`20260925T104354`) records the negative scenario producing **3 findings
where the correct answer is none**. `eval-regression` fails on it, which is precisely what that
job exists to do.

Phase 23's acceptance criterion "CI green on a clean clone" is therefore **not met**, and the gate
has not been weakened to claim it. Going green requires fixing the confabulation, not adjusting the
threshold. The remaining leak is restatement of a single source — see BUG-005 — and it is the
highest-value open defect in the project.

What the same run *did* improve, measured against the previous baseline:

| Metric | Before | Now |
|---|---|---|
| `intent_accuracy` | 0.459 | 0.574 |
| `dependency_correctness` | 0.667 | 0.833 |
| `replanning_success` | 0.411 | 0.658 |
| `task_efficiency` | 3.069 | 2.306 |
| `latency_s` | 91.8 | 45.2 |

`plan_validity` fell from 0.667 to 0.333, and that is honest rather than a regression in
behaviour: the metric counts plans passing with **zero repairs**, and the new terminal-task repair
fires on most plans. Previously those plans failed outright and produced nothing. The planner
needing help is now visible instead of fatal — but it is still the planner needing help, and the
number says so.

## Known gaps

- **No frontend test runner.** `tsc` and a production build run in CI, but there is no vitest, so
  `reconstruct()` in `useReplay.ts` — which rebuilds a run's state from its events — has no unit
  test. The weakest part of the test estate.
- **Three evaluation scenarios, not the twenty** the plan calls for.
- **Fault injection is manual.** "A deliberately broken planner drops `plan_validity`" is verified
  by hand, not by a scenario.
- **Three evaluation scenarios became eight**, where the plan calls for twenty.
