# JARVIS

**An adaptive, evidence-driven AI orchestration engine.**

JARVIS turns a high-level natural-language objective into a validated, executable task graph —
selecting tools, executing tasks with dependency awareness, reasoning over the evidence it
collects, detecting what evidence is *missing*, verifying its own candidate findings, and
replanning when the evidence is insufficient.

It is not a chat interface. You give it an objective; it works out how to accomplish it, and it
shows its work.

Built as Member 1's orchestration engine, it now also carries the work of **Member 3** (a knowledge
graph of entities, relationships and claims, with cross-document conflicts, a timeline and search)
and **Member 4** (a lexical verifier, a prompt-injection scanner, a trust benchmark and three tiers
of memory), ported into the same process and held to the same rules
([ADR-009](.claude/decisions/ADR-009-port-teammates-in-process.md)). Who built what is in
[`docs/contribution.md`](docs/contribution.md).

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
| Docker | any recent | Postgres (stored runs, memory of past missions) and Neo4j (the knowledge graph, facts across missions) — **not needed for the demo**; without them nothing is stored and knowledge graphs stay in memory |

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

Optional, for stored runs, memory, and the knowledge graph in Neo4j
([ADR-010](.claude/decisions/ADR-010-neo4j-knowledge-graph.md)):

```bash
docker compose up -d postgres neo4j   # Neo4j Browser: http://localhost:7474
cd backend && alembic upgrade head && cd ..
```

The migration is not optional once Postgres is up: without the tables, runs and memory are not
stored (the run itself still completes, and the log says why). Neo4j needs no setup; its
constraints are created on first use.

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

When it finishes, press **Knowledge graph** on the mission page: the run's entities in 3D (2D with
reduced motion), claims and documents unfolding beneath them. Hover a node for its details, click
one to light up everything related, click a finding to light up the evidence it rests on
([ADR-011](.claude/decisions/ADR-011-3d-knowledge-explorer.md)).

The other pages: `#/memory` (findings and entities across past missions, with Docker up),
`#/knowledge` (a knowledge graph from documents, no mission), `#/replay` (a recorded run replayed at
up to 20x), and `#/evaluation` (the committed evaluation reports, charted).

### 6. The tests

```bash
cd backend
pytest tests -m "not llm"      # 925 tests, no model needed
```

### 7. Reproduce the trust benchmark

Member 4's verifier benchmark (60 cases) and the prompt-injection suite (27 cases) need no model and
are deterministic, so their committed report can be reproduced exactly:

```bash
cd backend
python -m app.cli eval-trust --no-write        # 60/60, hallucination_rate 0.000, injection 27/27
python scripts/check_trust_reports.py          # compares a fresh run with the committed report
```

---

## The demo

[`docs/demo-script.md`](docs/demo-script.md) has nine demos with exact commands, what each one
proves, and a recorded fallback for when local inference stalls — which it occasionally does, and
which a presentation should not depend on. Demos 7-9 are the knowledge graph, a planted prompt
injection, and memory across missions.

---

## How it is measured

```bash
cd backend
python -m app.cli eval --suite all
```

Ten metrics, over **eleven scenarios** - three negative cases and one planted prompt injection, across three document families and three file formats - computed from real runs over datasets in
[`.agent/evals/datasets/`](.agent/evals/datasets/). Reports are written to
[`.agent/evals/reports/`](.agent/evals/reports/) and committed. **No number anywhere in this
repository is hand-written** — a report carries the model, prompt versions and a config hash, and
two reports produced with different stamps are refused as incomparable rather than quietly
compared.

The current baseline is `20261005T050619-qwen3-4b-all` (the `composite` verifier and the knowledge
pass on comparative questions, both chosen by experiment, and the BUG-019/BUG-021 fixes). Every
build threshold passes. Its headline numbers:

| Metric | Value | |
|---|---|---|
| `evidence_coverage` | 1.000 | every finding has resolved evidence |
| `unsupported_claim_rate` | 0.000 | the hallucination proxy |
| `tool_selection_accuracy` | 1.000 | |
| `dependency_correctness` | 0.844 | |
| `replanning_success` | 1.000 | gaps closed within the iteration ceiling - vacuous here, see below |
| `intent_accuracy` | 0.595 | |
| `task_efficiency` | 1.650 | tasks ÷ minimal sufficient tasks — lower is better |
| `plan_validity` | 0.636 | plans passing with **zero** repairs |
| `verification_success` | 0.970 | findings that survive the independent check |

Two of those deserve their explanation rather than a chart.

**`plan_validity` at 0.636** means four plans in eleven still need a deterministic repair before
they can execute. That is the planner needing help, and the metric says so instead of hiding it.
The repairs are recorded on the plan, so a repaired plan never counts as clean.

**`verification_success` at 0.970 is worth reading scenario by scenario**, because a verifier that
approves everything scores 1.000 and is worthless. It was 1.000 in Phase 33, when the baseline
verifier passed an invented finding. Experiment 004 made the `composite` verifier (the model check,
Member 4's lexical rule and the specifics check) the default: it rejected that finding and nothing
else, and the figure fell to 0.909. Two fixes then moved it to 0.970, and both are explained: the
invented finding is no longer produced at all (BUG-019; that scenario's 1.000 is vacuous, nothing to
verify), and "delivered on 9012", a shipment number taken for a date, is now caught (BUG-021; that
scenario fell from 1.000 to 0.667). The other nine scenarios did not move.

**The knowledge pass earned its place.** Experiment 003 turned it off: the agent then found nothing on
`shipment_arrival_conflict`, Member 3's own planted contradiction, which it finds with the pass on.
It costs about 16 s per scenario.

**`replanning_success` at 1.000 is vacuous.** No evidence gaps were detected in this run, so the
metric is 0 of 0 gaps closed. It says nothing about the replanning loop on this
baseline.

### The defect that kept CI red, and how it was fixed

**The agent used to invent a finding on a negative case** (BUG-019). Asked whether a consistent
report contradicts itself, it answered, in the Phase 34 baseline:

> *The Aurora project report states two different completion dates: 30 April 2026 and 31 January
> 2026*

It cited two lines, `r10` and `r12`. **31 January 2026 is on neither**: it is the M2 milestone on
`r13`. The claim was not a misreading of evidence, it was a value the evidence does not hold. The
composite verifier's specifics check noticed and marked it `PARTIALLY_SUPPORTED`, but a partially
supported contradiction is still reported, and a contradiction has no partial form: it *is* its two
values.

So the rule that already said "a claim of conflict must cite both sides" (BUG-005) now also says
**both of its values must be in the lines it cites**. When the objective asks for a comparison, a
fully cited claim that states a date or figure none of its cited lines contains is discarded before
verification, with the reason recorded as an event. Measured on the full suite (baseline
`20261005T050619`): the negative case produces nothing, and every positive scenario keeps exactly
the findings it had. CI's evaluation gate passes for the first time since BUG-019 appeared.

Two earlier changes had already reduced it, and neither was asking the model more firmly:

- A structural rule: **a claim of conflict must cite both sides.** When the intent requires a
  comparative operation, a claim fully supported by a single locator restates a source rather than
  answering the question. It reads the intent, not the claim — "extract the timeline" is answered
  by a single-source fact, and "do these conflict?" is not. (BUG-005.)
- **A claim that asserts an absence is not a finding.** "There is no contradiction" is true and
  uncitable: a finding is bound to the locators it rests on, and no locator says something is *not*
  there. A negative conclusion belongs in the report narrative, written from the fact that nothing
  was established. (BUG-014.)

**What BUG-019 also showed, and what still holds.** The model's output is stable within a session and
differs between them: the same code passed this scenario one hour and failed it the next. One
evaluation run is one sample. The rule above does not depend on which claim the model writes, which
is why it was chosen over another prompt change; but a different invented claim, citing a line that
*does* hold its values, would still need verification to catch it.

**Every positive scenario reports its planted findings.** `aurora_contradiction` finds both planted
contradictions (completion date and budget), each citing both documents. `shipment_arrival_conflict`
finds both of Member 3's dates. `injection_document` flags the planted instruction and does not obey
it, though it still does not state the real delivery date: the model writes weak claims there, and
the verifier now marks the worst of them (BUG-021, fixed in the verifier, not in the model).

That trade is worth understanding rather than glossing. Before these fixes the contradiction
scenario reported four findings — three of them restatements, counted as successes by every metric.
Removing them did not lower the agent's recall; it revealed it. The real figure was always about one
genuine contradiction per run, and the ceiling is the model: `qwen3:4b` does not reliably produce a
claim that pairs two documents.

Of the two possible failures this is the better one. An investigation that reports nothing is
honest; one that invents three findings is not. Tracked as BUG-005, BUG-012 and BUG-019 in
[`.claude/logs/bug-log.md`](.claude/logs/bug-log.md), and visible on the `#/evaluation` page.

## Architecture

A **modular monolith** with custom orchestration — no agent framework.
([ADR-001](.claude/decisions/ADR-001-modular-monolith.md),
[ADR-004](.claude/decisions/ADR-004-custom-orchestration.md).)

```
backend/app/
├── schemas/          15 modules, 116 types — every boundary is typed
├── llm/              the ONLY package that speaks to a model (invariant 1)
├── tools/            registry, loader, document tools, the knowledge-graph tool
├── intelligence/     intent · planner · graph · router · execution · context
│                     reasoning · evidence_gap · replanning · planning_policy · synthesis
│                     knowledge (Member 3) · trust (Member 4) · temporal
├── security/         prompt-injection scanning and safe wrapping (Member 4)
├── memory/           working · episodic · semantic memory across missions (Member 4)
├── integrations/     verifiers (baseline · lexical · composite) · Neo4j store (the only
│                     module that imports the driver) · context provider
├── orchestration/    the headless pipeline. CLI, API and UI all render one run
├── api/              FastAPI + SSE  (ADR-008): missions, knowledge, memory, replay
├── evaluation/       the metrics harness, the trust and security benchmarks
├── database/         async SQLAlchemy, 17 tables
└── core/             config, events, logging

frontend/src/         React + TypeScript — Mission Control, the 3D knowledge explorer
.agent/               prompts · config · fixtures · evals · traces  (behaviour, versioned)
.claude/              architecture · decisions · logs · testing  (why it is like this)
```

### What the integration added

| Subsystem | What it does | Where to read |
|---|---|---|
| **Knowledge layer** (Member 3) | Extracts entities, relationships and claims from each document, grounds every value on its source line, finds claims that conflict across documents, orders a timeline, searches with explained scores. Per run, never shared between runs | [`knowledge-layer.md`](.claude/architecture/knowledge-layer.md) |
| **Neo4j** | Holds each run's knowledge graph (and cross-run facts). Optional: when it is down, runs use the in-memory store, which answers identically - one test suite holds both to it | [ADR-010](.claude/decisions/ADR-010-neo4j-knowledge-graph.md) |
| **3D explorer** | The knowledge graph in Mission Control: nodes with sub-nodes, click to light up what is related, hover for details, a finding's evidence trail, 2D fallback | [ADR-011](.claude/decisions/ADR-011-3d-knowledge-explorer.md) |
| **Verification** (Member 4) | The `composite` verifier, the default by experiment: the model check, Member 4's lexical rule, and a check that every date and figure a claim states is in its cited lines | [`verification.md`](.claude/architecture/verification.md) |
| **Security** (Member 4) | Every document is scanned for prompt injection; a flag is reported, never used to drop evidence; untrusted text is wrapped in the prompts | [`security.md`](.claude/architecture/security.md) |
| **Memory** (Member 4) | Past missions' findings (every status) and facts (only from verified findings, with their support, no confidence). Written after a run; never read back into one | [`memory.md`](.claude/architecture/memory.md) |

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
8. **Knowledge is scoped per run.** Two runs in one Neo4j database never see each other.
9. **Memory never feeds a run.** No module a mission executes may import `app.memory`.
10. **Optional infrastructure never fails a run.** Postgres, Neo4j and memory each degrade to
    "not stored", contained and logged.

### Two configuration surfaces

`.env` sets **hard ceilings**; `.agent/config/*.yaml` expresses **behaviour policy** within them.
YAML can never exceed an `.env` ceiling — `clamp()` enforces it and logs every clamp, so a
silently-ignored setting is impossible.

---

## Where to read next

| | |
|---|---|
| The build order and status of all 36 phases | [`.claude/implementation/implementation-plan.md`](.claude/implementation/implementation-plan.md) |
| How Members 3 and 4 were integrated, phase by phase | [`.claude/implementation/integration-plan-phases-25-35.md`](.claude/implementation/integration-plan-phases-25-35.md) |
| Every teammate feature, and what became of it | [`.claude/integrations/teammate-port.md`](.claude/integrations/teammate-port.md) |
| Why the reasoning engine is shaped this way | [`.claude/architecture/reasoning-engine.md`](.claude/architecture/reasoning-engine.md) |
| Why verification sits outside the plan | [`.claude/architecture/verification.md`](.claude/architecture/verification.md) |
| The HTTP API | [`.claude/api/endpoints.md`](.claude/api/endpoints.md) · [`docs/openapi.json`](docs/openapi.json) |
| How the agent is measured | [`.claude/testing/agent-evaluation.md`](.claude/testing/agent-evaluation.md) |
| Every defect found, and what caused it | [`.claude/logs/bug-log.md`](.claude/logs/bug-log.md) |
| Every measurement that decided something | [`.claude/logs/experiment-log.md`](.claude/logs/experiment-log.md) |
| Architecture decisions | [`.claude/decisions/`](.claude/decisions/) |
| What this contributes, for a reviewer | [`docs/contribution.md`](docs/contribution.md) |

---

## Scope

This repository began as **Member 1** of a four-person system: intent, planning, tool selection
and reasoning — the orchestration brain.

Members 3 and 4 built their parts as separate prototypes. They were **ported into this codebase**,
with the same logic, typed and tested, rather than called as services
([ADR-009](.claude/decisions/ADR-009-port-teammates-in-process.md)): every feature, the original
file it came from and what changed is in
[`teammate-port.md`](.claude/integrations/teammate-port.md), and the originals are archived in
[`.claude/integrations/originals/`](.claude/integrations/originals/). Member 2's context retrieval
is still reached through a `Protocol` with a local fallback. See
[`.claude/context/member-1-scope.md`](.claude/context/member-1-scope.md).

## Status

Phases 0–24 built, and Phases 25–35 of the Members 3 and 4 integration complete
([plan](.claude/implementation/integration-plan-phases-25-35.md)). The evaluation gate passes on
the committed baseline since the BUG-019 fix. It was red until then, deliberately, and was never
weakened to make it green.
