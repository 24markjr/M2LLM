# Architecture

**Shape:** modular monolith (ADR-001). One deployable backend, hard internal boundaries,
clear future service seams.

This is the orientation document. Subsystem detail lives in [`../architecture/`](../architecture/).

---

## System view

```
                      React (Mission Control)
                              |
                         HTTP + SSE
                              |
                           FastAPI
                              |
                    +-----------------+
                    |  Agent Runtime  |
                    +-----------------+
                              |
   +--------------+-----------+-----------+--------------+
   |              |                       |              |
Intent        Planner               Tool Router      Context
Engine           |                       |           Manager
   |             v                       |              |
   |        Task Graph  <----------------+              |
   |             |                                      |
   |             v                                      |
   |      Execution Engine  -------> Tools -------------+
   |             |                     |
   |             v                     +--> M2Context   (Member 2)
   |        Observations               +--> Knowledge   (Member 3)
   |             |                     +--> Verification(Member 4)
   |             v
   |      Reasoning Engine
   |             |
   |             v
   |     Findings + Evidence
   |             |
   |             v
   |        Verification
   |          /      \
   |    SUPPORTED   NOT SUPPORTED
   |         |            |
   |         |     Evidence Gap Detector
   |         |            |
   |         |       Replanning  ------> (mutates Task Graph)
   |         |            |
   |         +-----<------+
   |         |
   |         v
   |     Synthesis
   |         |
   +---------+--------> PostgreSQL + pgvector
                         (runs, tasks, tools, findings,
                          evidence, verifications, events, chunks)
```

Everything above the database emits to the **event bus**, which persists the run timeline,
feeds the SSE stream, and optionally writes trace files.

---

## The one-way door

```
   any intelligence component
              |
              v
      app/llm/provider.py      <-- the ONLY door to a language model
              |
      OllamaProvider | EchoProvider
```

Invariant #1. Enforced by `tests/unit/test_llm_isolation.py`, which fails if any module
outside `app/llm/` imports httpx or references `OLLAMA_*`.

This is what makes the claim "the LLM is a component, not the architecture" checkable rather
than rhetorical.

---

## Package layout

```
backend/app/
├── api/              FastAPI routers, SSE streaming            (19)
├── core/             config, event bus, logging                 (0, 5)
├── database/         session, repositories                      (3)
├── models/           SQLAlchemy models                          (3)
├── schemas/          Pydantic domain types — the typed spine    (2)
├── llm/              provider protocol, structured output       (4)
├── tools/            registry + built-in tools                  (9)
├── integrations/     M2Context, knowledge, verification adapters (12, 15)
├── evaluation/       harness, scorers, regression               (20)
└── intelligence/
    ├── intent/       objective -> Intent                        (6)
    ├── planner/      Intent -> validated Plan                   (7)
    ├── graph/        the mutable task DAG                       (8)
    ├── router/       task -> tool                               (10)
    ├── execution/    scheduler, retry, fallback, budget         (11)
    ├── context/      working memory, compaction, retrieval      (12)
    ├── reasoning/    observations -> findings                   (13)
    ├── evidence_gap/ findings -> typed gaps -> proposed tasks   (14)
    ├── replanning/   the closed loop                            (16)
    ├── planning_policy/ cost-aware action selection             (17)
    └── synthesis/    findings -> final report                   (18)
```

Numbers are the phase that creates the package.

---

## Data flow through one run

| # | Stage | Input | Output | Persists |
|---|---|---|---|---|
| 1 | Intent | objective text, attachments | `Intent` | `agent_runs` |
| 2 | Planning | `Intent`, tool catalogue | validated `Plan` | `tasks`, `task_dependencies` |
| 3 | Graph | `Plan` | `TaskGraph` | task states |
| 4 | Routing | `Task` | `ToolSelection` | `TOOL_SELECTED` event |
| 5 | Execution | `ToolCall` | `Observation` | `tool_executions` |
| 6 | Context | observations | working memory | `document_chunks` |
| 7 | Reasoning | observations, evidence | `Finding[]` | `findings`, `evidence` |
| 8 | Verification | claim + evidence | `VerificationResult` | `verifications` |
| 9 | Gap detection | unsupported findings | `EvidenceGap[]` | `EVIDENCE_GAP_DETECTED` |
| 10 | Replanning | gaps, failures | graph mutations | `PlanRevision` |
| 11 | Synthesis | verified state | `FinalReport` | `agent_runs.final_result` |

Every transition emits an `ExecutionEvent`. The run is reconstructable from the event log
alone (invariant #4) — which is what makes the trace a genuine artifact rather than a log.

---

## Three architectural choices worth knowing up front

**1. The planner proposes; the validator disposes.**
The model generates a candidate decomposition. Application code checks it for cycles,
dangling dependencies, orphan tasks and intent coverage, repairs what is deterministically
repairable, and re-prompts at most twice before failing cleanly. Plan validity is a property
of the system, not a hope about the model.

**2. Confidence is computed, never asked for.**
The reasoning engine's evidence binder resolves every citation against actually-retrieved
content. Confidence is a pure function of resolution rate, evidence strength, source
agreement and classification. This is the mechanism that makes evidence-gap detection
deterministic rather than a matter of the model's mood.

**3. Verification does not see the reasoning.**
The baseline verifier receives only the claim and its evidence text. A verifier with access
to the reasoning trail tends to be persuaded by it, which defeats the purpose of verifying.

---

## Future service seams

The monolith is drawn so it can be cut without redesign (ADR-001). The natural boundaries,
should scale ever require them:

| Extractable | Why it is already separable |
|---|---|
| Execution engine + tool runtime | Communicates via `Task` / `ToolCall` / `Observation` only |
| Verification | Already a provider protocol with a remote implementation |
| Context + retrieval | Already a provider protocol |
| Evaluation harness | Reads persisted runs; no runtime coupling |

Nothing about the MVP depends on that happening.
