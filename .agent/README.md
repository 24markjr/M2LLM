# `.agent/` — the executable agent specification

This directory answers exactly one question:

> **How do we know the JARVIS agent actually works?**

Nothing else goes here. It is not a scratch folder, not a docs folder, and not a place for
source code. If a file does not help prove or configure agent behaviour, it belongs
somewhere else.

The distinction that matters:

| Directory | Question it answers |
|---|---|
| `.agent/` | *Does the agent behave correctly?* — behaviour, configuration, evidence |
| `.claude/` | *Why is it built this way?* — architecture, decisions, history |
| `backend/tests/` | *Do the Python units work?* — functions, classes, transitions |

`backend/tests/` tests code. `.agent/` tests **the agent as a system** — end-to-end
behaviour that no unit test can capture, like "when evidence is insufficient, does it
identify what is missing and go get it?"

---

## Layout

```
.agent/
├── config/       agent behaviour policy (versioned, loaded and validated)
├── prompts/      prompt assets — versioned like code, never string literals in Python
├── scenarios/    end-to-end behaviour specifications with expected outcomes
├── tests/        component-level agent test cases (intent, planner, router, ...)
├── evals/        the measurement system: datasets, expectations, scorers, reports
├── traces/       recorded execution traces — demo fallbacks and regression baselines
└── fixtures/     input documents, CSVs and expected extractions
```

---

## `config/` — behaviour policy, not infrastructure

There are two configuration surfaces in this project, and the split is deliberate:

| Surface | Holds | Changed by |
|---|---|---|
| `.env` → `app.core.config.Settings` | **Where things are and hard safety ceilings**: database URL, provider selection, `MAX_REPLAN_ITERATIONS`, `MAX_PARALLEL_TASKS` | Operators, per machine |
| `.agent/config/*.yaml` | **How the agent behaves**: model roles, tool fallback chains, scoring weights, evaluation thresholds | The agent engineer, committed and reviewed |

**Rule: the YAML can never exceed an `.env` ceiling.** `Settings` values are hard caps
enforced at load time. If `agent.yaml` requests 8 replan iterations and
`MAX_REPLAN_ITERATIONS=3`, the loader clamps to 3 and logs it. Behaviour policy is tunable;
safety bounds are not tunable from inside the repo.

| File | Consumed by |
|---|---|
| `agent.yaml` | Runtime loop policy, phase toggles, termination conditions — Phase 16 |
| `models.yaml` | Per-role model assignment and generation parameters — Phase 4 |
| `tools.yaml` | Tool enablement, fallback chains, cost hints — Phases 9/10/17 |
| `evaluation.yaml` | Metric thresholds and regression tolerances — Phase 20 |

## `prompts/` — versioned assets

Every prompt the system sends lives here as Markdown, never as a Python string literal
(ADR-003, invariant #1). Reasons:

- A prompt change is a reviewable diff
- Evaluation reports stamp the prompt version, so results are comparable
- A prompt can be inspected without reading engine code

Each prompt file documents its **inputs**, its **expected output schema**, and the phase
that owns it. Prompts are loaded by `app.llm.prompts` (Phase 4).

## `scenarios/` — end-to-end behaviour

A scenario is a complete specification of one agent behaviour: the objective, the fixtures,
what the agent is expected to *do*, and what must appear in the execution trace. Scenarios
are how the six demos are proven, and how they stay proven.

The schema is defined in `scenarios/README.md`.

## `tests/` — component-level agent cases

Table-driven cases for one component at a time: given this intent, expect these operations;
given this task, expect this tool. These catch regressions that a full scenario would also
catch, but faster and with a precise failure location.

## `evals/` — the measurement system

| Subdirectory | Contents |
|---|---|
| `datasets/` | Scenario inputs used for measurement (≥ 20 by Phase 20, including negative cases) |
| `expected_outputs/` | Expected intents, DAG edge sets, findings — the ground truth |
| `scoring/` | One scorer per metric; each is independently testable |
| `reports/` | Generated reports, committed. These are the numbers we present. |

**No metric is ever hard-coded.** Every number in a report is computed by a scorer from a
real run. This is invariant #5 and it is not negotiable — a fabricated evaluation would
make the entire project worthless.

## `traces/` — recorded runs

Real execution traces, produced by real runs with `TRACE_TO_FILE=1`. Two uses:

1. **Regression baselines** — has the agent's behaviour changed unexpectedly?
2. **Demo insurance** — the UI can replay a trace (Phase 22), so a live model failing
   during a presentation does not end the presentation.

Traces are never hand-authored. A hand-written trace is a fabricated result.

## `fixtures/` — investigation inputs

The documents, CSVs and expected extractions that scenarios run against. Fixtures are
deliberately small and deliberately flawed: they contain the contradictions, the missing
baselines and the conflicting dates that the agent is supposed to find.

---

## Status

Phase 1 establishes this structure and its contracts. Files arrive as their phases land:

| Phase | Adds |
|---|---|
| 4 | `prompts/` loader; `config/models.yaml` consumed |
| 6 | `prompts/intent.md`, `tests/test_intent.yaml` |
| 7 | `prompts/planner.md`, `tests/test_planner.yaml` |
| 9 | `fixtures/documents/`, first real trace, `config/tools.yaml` consumed |
| 10 | `prompts/router.md`, `tests/test_router.yaml` |
| 13 | `prompts/reasoning.md`, `scenarios/contradiction_detection.yaml` |
| 14 | `prompts/evidence_gap.md`, `scenarios/evidence_gap.yaml` |
| 15 | `prompts/verification.md` |
| 16 | `scenarios/replanning.yaml`, `config/agent.yaml` consumed |
| 18 | `prompts/synthesis.md` |
| 20 | `evals/` in full, `config/evaluation.yaml` consumed |
