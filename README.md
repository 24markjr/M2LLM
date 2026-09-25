# JARVIS

**An adaptive, evidence-driven AI orchestration engine.**

JARVIS turns a high-level natural-language objective into a validated, executable task graph —
selecting tools, executing tasks with dependency awareness, reasoning over the evidence it
collects, detecting what evidence is *missing*, verifying its own candidate findings, and
replanning when the evidence is insufficient.

It is not a chat interface. You give it an objective; it works out how to accomplish it, and it
shows its work.

```
USER OBJECTIVE → INTENT → PLAN → TASK GRAPH → TOOL ROUTING → EXECUTION
      → OBSERVATION → REASONING → FINDINGS → VERIFICATION
             ↓ evidence insufficient
        EVIDENCE GAP → REPLAN → (execute again)
             ↓ evidence sufficient
        SYNTHESIS → EVIDENCE-BACKED REPORT
```

---

## The idea worth arguing about

Most systems built on a language model ask it how confident it is. This one never does.

**Every claim is bound to the evidence that produced it.** A finding cites source locators —
`aurora_project_report.txt:r12` — and those citations are resolved against locators the tasks
actually returned. A citation that cannot be resolved is kept and marked `UNRESOLVED`, never
dropped, because a dropped bad citation leaves a claim that looks fully supported.

Confidence is then *computed* from what resolved:

```python
Confidence.compute(refs=refs, source_agreement=..., classification=...)
```

`Confidence(value=0.96)` raises a `ValidationError`. There is no constructor that takes a bare
number, so no code path in the system can assert a confidence it did not derive. That is enforced
in the type, not in a convention — a convention is something a future contributor can be unaware
of.

Three consequences follow, and they are the reason the rest of the architecture looks the way it
does:

- **An empty result is a valid answer.** Asked whether a document contradicts itself when it does
  not, the correct output is no findings. The evaluation suite fails the build if the agent
  invents one.
- **Verification is independent.** It runs on every finding, outside the plan, and does not see
  the reasoning it is checking. When it has to fall back to the weaker local verifier it says so;
  a check that quietly got weaker is worse than no check.
- **The plan is not sacred.** When verification rejects a finding and gap detection names the
  specific missing element, a task is inserted into the graph *while it is running*.

---

## Quickstart

Verified from a clean clone on Windows 11 and Linux. If any step here does not work, that is a
bug in this file.

### Prerequisites

| | Version | Needed for |
|---|---|---|
| Python | 3.12 | everything |
| [Ollama](https://ollama.com) | any recent | the model |
| Node | 20+ | the web console only |
| Docker | any recent | Postgres only — **not needed for the demo** |

### 1. The model

```bash
ollama pull qwen3:4b
ollama pull nomic-embed-text
```

`qwen3:4b` runs on a laptop. It is also a small model, and the numbers in
[the evaluation reports](.agent/evals/reports/) reflect that honestly.

### 2. Install

```bash
git clone https://github.com/24markjr/M2LLM.git
cd M2LLM
python -m venv .venv

# Windows
.venv\Scripts\activate
# macOS / Linux
source .venv/bin/activate

pip install -e "backend[dev]"
```

### 3. Check it can run

```bash
cd backend
python -m app.cli health
```

Reports the provider, the model, and whether it answered. If this fails, nothing below will work.

### 4. Run an investigation

```bash
python -m app.cli investigate \
  "Investigate the Aurora project reports and identify any contradictions between the timeline and the financial information." \
  --docs aurora_project_report.txt aurora_financial_report.txt aurora_budget.csv \
  --report aurora.md
```

Takes roughly 45–90 seconds on `qwen3:4b`. You will see the intent, the validated task graph,
which tasks run in parallel, tool routing decisions, findings with their evidence, verification
verdicts, and the final report.

Document names resolve inside [`.agent/fixtures/`](.agent/fixtures/), or you can pass a path to
your own `.txt`, `.md`, `.csv` or `.pdf`.

### 5. The web console (optional)

```bash
# terminal 1
cd backend && uvicorn app.api.app:create_app --factory --reload

# terminal 2
cd frontend && npm install && npm run dev
```

Open <http://localhost:5173>. The Aurora objective and documents are prefilled — click **New
mission** then **Start mission** and watch it run live over SSE.

There is also `#/replay`, which replays a recorded run at up to 20x, and `#/evaluation`, which
charts the committed evaluation reports.

### 6. The tests

```bash
cd backend
pytest tests -m "not llm"      # 581 tests, no model needed
```

---

## The demo

[`docs/demo-script.md`](docs/demo-script.md) has six demos with exact commands, what each one
proves, and a recorded-trace fallback for when local inference stalls — which it occasionally
does, and which a presentation should not depend on.

---

## How it is measured

```bash
cd backend
python -m app.cli eval --suite all
```

Ten metrics, over **eight scenarios** - two of them negative cases, across two document families and three file formats - computed from real runs over datasets in
[`.agent/evals/datasets/`](.agent/evals/datasets/). Reports are written to
[`.agent/evals/reports/`](.agent/evals/reports/) and committed. **No number anywhere in this
repository is hand-written** — a report carries the model, prompt versions and a config hash, and
two reports produced with different stamps are refused as incomparable rather than quietly
compared.

The current baseline is `20260925T115350-qwen3-4b-all`. Its headline numbers:

| Metric | Value | |
|---|---|---|
| `evidence_coverage` | 1.000 | every finding has resolved evidence |
| `unsupported_claim_rate` | 0.000 | the hallucination proxy |
| `tool_selection_accuracy` | 1.000 | |
| `dependency_correctness` | 0.848 | |
| `replanning_success` | 0.787 | gaps closed within the iteration ceiling |
| `intent_accuracy` | 0.628 | |
| `task_efficiency` | 1.756 | tasks ÷ minimal sufficient tasks — lower is better |
| `plan_validity` | 0.625 | plans passing with **zero** repairs |

Two of those deserve their explanation rather than a chart.

**`plan_validity` at 0.625** means three plans in eight still need a deterministic repair before
they can execute. That is the planner needing help, and the metric says so instead of hiding it.
The repairs are recorded on the plan, so a repaired plan never counts as clean.

**`verification_success` is 0.750, and 1.000 would be a worry rather than a win.** A verifier that
approved everything would score perfectly and be worthless.

### The open defect, stated plainly

**Fixed: the agent no longer invents findings.** Both negative scenarios — one asking whether a
consistent report contradicts itself, one asking the same of a budget CSV — produce **zero
findings**, which is the correct answer. `unsupported_claim_rate` is 0.000 and
`evidence_coverage` is 1.000.

Two changes did it, and neither was asking the model more firmly:

- A structural rule: **a claim of conflict must cite both sides.** When the intent requires a
  comparative operation, a claim fully supported by a single locator restates a source rather than
  answering the question. It reads the intent, not the claim — "extract the timeline" is answered
  by a single-source fact, and "do these conflict?" is not. (BUG-005.)
- **A claim that asserts an absence is not a finding.** "There is no contradiction" is true and
  uncitable: a finding is bound to the locators it rests on, and no locator says something is *not*
  there. A negative conclusion belongs in the report narrative, written from the fact that nothing
  was established. This was a contradiction between two of my own prompts, and the second negative
  scenario is what exposed it.

**What remains:** two positive scenarios produce **no findings where claims are planted**
(`aurora_contradiction`, `aurora_pdf_timeline`). The build fails on that, and the threshold has not
been moved.

That trade is worth understanding rather than glossing. Before these fixes the contradiction
scenario reported four findings — three of them restatements, counted as successes by every metric.
Removing them did not lower the agent's recall; it revealed it. The real figure was always about one
genuine contradiction per run, and the ceiling is the model: `qwen3:4b` does not reliably produce a
claim that pairs two documents.

Of the two possible failures this is the better one. An investigation that reports nothing is
honest; one that invents three findings is not. Tracked as BUG-005 and BUG-012 in
[`.claude/logs/bug-log.md`](.claude/logs/bug-log.md), and visible on the `#/evaluation` page.

## Architecture

A **modular monolith** with custom orchestration — no agent framework.
([ADR-001](.claude/decisions/ADR-001-modular-monolith.md),
[ADR-004](.claude/decisions/ADR-004-custom-orchestration.md).)

```
backend/app/
├── schemas/          12 modules, 97 types — every boundary is typed
├── llm/              the ONLY package that speaks to a model (invariant 1)
├── tools/            registry, loader, built-in document tools
├── intelligence/     intent · planner · graph · router · execution · context
│                     reasoning · evidence_gap · replanning · planning_policy · synthesis
├── orchestration/    the headless pipeline. CLI, API and UI all render one run
├── api/              FastAPI + SSE  (ADR-008)
├── evaluation/       the metrics harness
├── database/         async SQLAlchemy, 11 tables
└── core/             config, events, logging

frontend/src/         React + TypeScript — Mission Control
.agent/               prompts · config · fixtures · evals · traces  (behaviour, versioned)
.claude/              architecture · decisions · logs · testing  (why it is like this)
```

### Invariants

These are not aspirations. Each one has a test that fails if it is violated — see
[`.claude/testing/testing-strategy.md`](.claude/testing/testing-strategy.md).

1. **The LLM is reached only through `app/llm/`.** Enforced by parsing the source tree.
2. **Every boundary is typed.** No dicts crossing components.
3. **No model deliberation is ever persisted.** Redacted on the event bus before any sink.
4. **A run is reconstructable from its events.** Append-only, with offsets relative to
   `RUN_STARTED`.
5. **No fabricated behaviour.** No hand-written trace, metric or report anywhere.
6. **Closed vocabularies.** Operations, task types, statuses and event types are fixed sets.
7. **Every loop is bounded.** Every ceiling is configured, and a new `while True` fails the build
   until its exit condition is written down.

### Two configuration surfaces

`.env` sets **hard ceilings**; `.agent/config/*.yaml` expresses **behaviour policy** within them.
YAML can never exceed an `.env` ceiling — `clamp()` enforces it and logs every clamp, so a
silently-ignored setting is impossible.

---

## Where to read next

| | |
|---|---|
| The build order and status of all 25 phases | [`.claude/implementation/implementation-plan.md`](.claude/implementation/implementation-plan.md) |
| Why the reasoning engine is shaped this way | [`.claude/architecture/reasoning-engine.md`](.claude/architecture/reasoning-engine.md) |
| Why verification sits outside the plan | [`.claude/architecture/verification.md`](.claude/architecture/verification.md) |
| The HTTP API | [`.claude/api/endpoints.md`](.claude/api/endpoints.md) · [`docs/openapi.json`](docs/openapi.json) |
| How the agent is measured | [`.claude/testing/agent-evaluation.md`](.claude/testing/agent-evaluation.md) |
| Every defect found, and what caused it | [`.claude/logs/bug-log.md`](.claude/logs/bug-log.md) |
| Architecture decisions | [`.claude/decisions/`](.claude/decisions/) |
| What this contributes, for a reviewer | [`docs/contribution.md`](docs/contribution.md) |

---

## Scope

This repository is **Member 1** of a four-person system: intent, planning, tool selection and
reasoning — the orchestration brain.

Members 2, 3 and 4 own context retrieval, knowledge search and verification. Each is reached
through a `Protocol` selected by environment variable, each has a local fallback so this side is
never blocked, and **no member's implementation is ever imported directly**. See
[`.claude/context/member-1-scope.md`](.claude/context/member-1-scope.md).

## Status

Phases 0–24 built. CI is red on `main`, deliberately: the evaluation gate fails on the
under-reporting described above, and the gate has not been weakened to make it green.
