# JARVIS — Member 1 Implementation Plan

**Scope:** Intelligence, Agent Orchestration & Decision Engine
**Owner:** Member 1
**Status:** Draft v1 — approved for execution
**Created:** 2026-09-23
**Repo state at authoring:** empty directory `D:\M2LLM`; Python 3.12.10, Node 24.19.0, Docker 29.8.0, git 2.55 available; Ollama and PostgreSQL not yet installed.

---

## 0. How to read this document

This is the single source of truth for build order. Every phase is a **vertical, testable increment** — no phase ends with dead code that nothing calls.

Each phase specifies:

| Field | Meaning |
|---|---|
| **Goal** | The one sentence that justifies the phase |
| **Why now** | The dependency reason it sits at this position |
| **Build** | Concrete files/modules produced |
| **Contracts** | Types or interfaces that cross a component boundary |
| **Acceptance** | Objective, checkable exit conditions |
| **Tests** | Unit / integration / agent-scenario coverage added |
| **Docs** | `.claude` files that must be updated before the phase is closed |
| **Effort** | Estimated focused work sessions (1 session ≈ 2–3 hours) |

**Status legend for tracking:** `TODO` · `IN PROGRESS` · `BLOCKED` · `DONE` · `DEFERRED`

---

## Progress

*Last updated 2026-09-25 at commit `24ba600`. Kept here rather than per section so there is one
place to read the state of the build.*

| # | Phase | Status | Notes |
|---|---|---|---|
| 0 | Foundations & tooling | `DONE` | Docker/Postgres blocked on WSL2 at the time; resolved |
| 1 | Configuration surfaces | `DONE` | `.env` ceilings vs `agent.yaml` policy, `clamp()` logs every clamp |
| 2 | Typed schemas | `DONE` | 12 modules, 97 types |
| 3 | Database persistence | `DONE` | 11 tables; **API runs are not yet persisted** |
| 4 | LLM provider layer | `DONE` | Invariant 1 boundary; Ollama constrained decoding |
| 5 | Prompt library | `DONE` | Strict `{{placeholder}}` rendering, versioned prompts |
| 6 | Intent analysis | `DONE` | Prompt v2; `SUPPORTING_OPERATIONS` (BUG-010) |
| 7 | Task planning | `DONE` | Prompt v2; terminal-task repair; type synonyms (BUG-009) |
| 8 | Event log | `DONE` | Append-only, `t_offset_ms` relative to `RUN_STARTED` |
| 9 | Tool registry | `DONE` | |
| 10 | Tool routing | `DONE` | Deterministic-first; LLM tiebreak only on ties |
| 11 | Execution engine | `DONE` | Concurrent by wave |
| 12 | Context management | `DONE` | `compact()` preserves every locator |
| 13 | Reasoning & evidence binding | `DONE` | Relevance gate added (BUG-005); see `architecture/reasoning-engine.md` |
| 14 | Evidence gap detection | `DONE` | Gap decision is deterministic |
| 15 | Verification | `DONE` | Degradation declared, never hidden; `architecture/verification.md` |
| 16 | Adaptive replanning | `DONE` | Bounded; every stop records a distinct reason |
| 17 | Planning policy | `DONE` | Insertion capped at 3 per iteration |
| 18 | Report synthesis | `DONE` | Every figure counted, not described |
| 19 | FastAPI + SSE | `DONE` | Built before 21 out of order — see `phase-09-api.md` |
| 20 | Evaluation harness | `DONE` | Baseline re-run 2026-09-25 (`20260925T104354`) and current. 3 scenarios, not the 20 the plan calls for |
| 21 | Frontend: Mission Control | `DONE` | React only; Tailwind/Query/Zustand/Recharts/Framer omitted — `frontend/README.md` |
| 22 | Live execution visualization | `DONE` | Replay (demo insurance), evaluation dashboard, animated replan insertion |
| 23 | Test hardening & CI | `DONE`, gate red | 581 tests, invariant + adversarial suites, GitHub Actions. `eval-regression` correctly fails on the baseline's confabulation - see testing-strategy.md |
| 24 | Documentation & demo package | `DONE`, 2 caveats | README rewritten, six-demo script, contribution statement, changelog current. 4 of 6 demos have a recorded fallback; a clean clone has not been tested from scratch |

**Carried debt**

1. **The confabulation is fixed** (BUG-005): the negative scenario now produces 0 findings,
   `unsupported_claim_rate` 0.000, `evidence_coverage` 1.000. **What replaced it:** the
   contradiction scenario yields 0-1 findings where 2 are planted, so the build is still red on
   the opposite criterion. Removing three restatements from that scenario did not lower recall, it
   exposed it - the ceiling is `qwen3:4b` not reliably pairing two documents in one claim.
2. **Three places construct the replanning pipeline** - `app/cli.py`, the orchestrator and
   `app/evaluation/runner.py`. This already cost two wasted evaluation runs: the BUG-005 fix was
   wired into one copy and silently did not apply to the others. They should collapse onto
   `app/orchestration/mission.py`.
3. The API does not persist runs — `DatabaseEventSink` exists but is not wired into the registry.
4. Phases 1–18 and 20 have no development-log entries; their reasoning is in commit messages and
   `bug-log.md`.

---

## 1. Invariants — rules that apply to every phase

These are non-negotiable and are checked at every phase gate.

1. **The LLM is a component, not the architecture.** No module may call the model directly except through `app/llm/provider.py`. Enforced by a lint test that greps for `ollama`/`httpx.post` outside the provider package.
2. **Typed boundaries.** Anything crossing a component boundary is a Pydantic model from `app/schemas/`. No raw `dict` in a public function signature.
3. **No hidden chain-of-thought.** Emitted events and reports expose *operational* transparency (task chosen, tool chosen, evidence retrieved, verification outcome, replan decision) — never raw model deliberation.
4. **Every run is traceable.** Every state transition writes an `ExecutionEvent`. A run must be fully reconstructable from its event log alone.
5. **No fabricated behaviour.** No mock progress logs, no simulated agent output presented as real, no hard-coded evaluation numbers. Mocks are allowed only in named fixtures and must be obviously named `Mock*`.
6. **No single-file logic dumps.** Each intelligence component is a package with `__init__.py`, an engine module, a prompt reference, and a test module.
7. **Bounded loops.** Every adaptive loop has a hard ceiling (`MAX_REPLAN_ITERATIONS`, `MAX_TASK_RETRIES`, `MAX_TOOL_CALLS_PER_RUN`) read from config, never hard-coded at the call site.
8. **Determinism where possible.** Model temperature, seeds, and tool ordering are configured, not incidental. Evaluation runs pin them.
9. **Docs move with code.** A phase is not `DONE` until `.claude/changes/changelog.md` and `.claude/logs/development-log.md` are updated; architectural changes additionally require an ADR.
10. **External members are interfaces, not assumptions.** M2Context, Member 3 (knowledge), Member 4 (verification) are consumed via provider protocols with working local fallbacks, so Member 1 is never blocked.

### Definition of Done (per phase)

- [ ] Code implemented in the specified locations
- [ ] Unit tests pass (`pytest backend/tests`)
- [ ] Relevant `.agent/scenarios` run green
- [ ] Relevant `.agent/evals` metric recorded (from Phase 14 onward)
- [ ] `.claude` architecture/implementation doc written or updated
- [ ] `changelog.md` + `development-log.md` entries added
- [ ] Files changed, tests executed, known issues reported in the session summary

---

## 2. Phase map

| # | Phase | Milestone | Effort | Depends on |
|---|---|---|---|---|
| 0 | Environment & bootstrap | — | 1 | — |
| 1 | Repo skeleton, `.agent` + `.claude` | — | 1–2 | 0 |
| 2 | Domain schemas (typed spine) | — | 2 | 1 |
| 3 | Database & persistence | — | 2 | 2 |
| 4 | LLM abstraction layer | — | 2 | 2 |
| 5 | Event bus & execution trace | — | 1 | 2,3 |
| 6 | Intent engine | — | 2 | 4,5 |
| 7 | Planner → validated DAG | — | 3 | 6 |
| 8 | Task graph engine | — | 2 | 7 |
| 9 | Tool system & registry | **M1: vertical slice** | 3 | 8 |
| 10 | Tool router | — | 2 | 9 |
| 11 | Execution engine | **M2: real execution** | 3 | 10 |
| 12 | Context manager & retrieval | — | 2 | 3,11 |
| 13 | Reasoning engine | — | 3 | 12 |
| 14 | Evidence gap detector | **M3: headline #1** | 3 | 13 |
| 15 | Verification integration | — | 2 | 13 |
| 16 | Adaptive replanning loop | **M4: headline #2** | 3 | 14,15 |
| 17 | Cost-aware action selection | — | 2 | 16 |
| 18 | Synthesis & final report | — | 2 | 16 |
| 19 | FastAPI + SSE streaming | **M5: API complete** | 3 | 18 |
| 20 | Agent evaluation harness | — | 3 | 19 |
| 21 | Frontend — Mission Control | — | 3 | 19 |
| 22 | Live execution visualization | — | 3 | 21 |
| 23 | Test hardening & CI | — | 2 | 20,22 |
| 24 | Documentation & demo package | **Ship** | 2 | 23 |

**Total:** ~55 sessions. Phases 0–11 are the critical path to a defensible demo; 12–18 are the differentiators; 19–24 are presentation and proof.

### Mapping to the original 20-step build order

| Original step | This plan |
|---|---|
| 1 Repository analysis | 0 + 1 |
| 2 Architecture + schemas | 1 + 2 |
| 3 Database | 3 |
| 4 LLM abstraction | 4 |
| 5 Intent engine | 6 (plus 5, event bus, pulled forward) |
| 6 Planner | 7 |
| 7 Task graph | 8 |
| 8 Tool system | 9 |
| 9 Execution engine | 10 + 11 |
| 10 Reasoning engine | 12 + 13 |
| 11 Evidence gap detector | 14 |
| 12 Verification integration | 15 |
| 13 Adaptive replanning | 16 (+ 17 cost-aware) |
| 14 Agent evaluation | 20 |
| 15 FastAPI | 18 + 19 |
| 16 React UI | 21 |
| 17 Live execution visualization | 22 |
| 18 Tests | 23 |
| 19 Documentation | 24 |
| 20 Demo | 24 |

Event bus (5) and context manager (12) are explicit phases rather than implicit work, because tracing and retrieval are load-bearing for the evaluation story.

---

# STAGE A — FOUNDATION (Phases 0–5)

## Phase 0 — Environment & bootstrap

**Goal:** A reproducible local environment where Postgres+pgvector and a local model both answer a health check.

**Why now:** Every later phase assumes a running model and database. Discover environment problems before writing logic, not during debugging.

**Build**

- `git init`, `.gitignore` (Python, Node, `.env`, `__pycache__`, `node_modules`, `.venv`, `traces/*.local.json`)
- `docker-compose.yml` — services: `postgres` (image `pgvector/pgvector:pg16`), `backend`, `frontend`, optional `ollama`
- `.env.example` with every variable the system reads:

```
APP_ENV=local
DATABASE_URL=postgresql+asyncpg://jarvis:jarvis@localhost:5432/jarvis
LLM_PROVIDER=ollama
OLLAMA_BASE_URL=http://localhost:11434
OLLAMA_MODEL=qwen3
OLLAMA_TIMEOUT_S=120
EMBEDDING_MODEL=nomic-embed-text
MAX_REPLAN_ITERATIONS=3
MAX_TASK_RETRIES=2
MAX_PARALLEL_TASKS=4
MAX_TOOL_CALLS_PER_RUN=40
LOG_LEVEL=INFO
```

- `backend/pyproject.toml` (or `requirements.txt` + `requirements-dev.txt`): fastapi, uvicorn, pydantic v2, pydantic-settings, sqlalchemy 2.x, asyncpg, alembic, httpx, pgvector, structlog, pytest, pytest-asyncio, ruff, mypy
- `scripts/dev-up.ps1` and `scripts/dev-up.sh` — one command brings the stack up
- `scripts/healthcheck.py` — verifies Postgres reachable, `vector` extension installable, Ollama `/api/tags` returns the configured model

**Acceptance**

- `docker compose up -d postgres` → `SELECT 1` succeeds from the host
- `CREATE EXTENSION IF NOT EXISTS vector;` succeeds
- Ollama installed, model pulled, `python scripts/healthcheck.py` prints all-green
- `ruff check` and `mypy` run clean on an empty package

**Known risk:** Ollama is not currently installed on this machine. If a local install is blocked, Phase 4's provider abstraction still lets work continue against a deterministic `EchoProvider` fixture — but flag it in the development log rather than silently switching.

**Docs:** `.claude/context/tech-stack.md`, `.claude/decisions/ADR-002-postgresql.md`, `ADR-003-ollama.md`, `ADR-005-pgvector.md`

**Effort:** 1 session

---

## Phase 1 — Repository skeleton, `.agent` and `.claude`

**Goal:** The directory structure and engineering-memory system exist before any logic, so nothing lands in the wrong place.

**Why now:** Retrofitting structure is expensive, and the `.agent`/`.claude` discipline is part of the contribution, not decoration.

**Build**

Repository root:

```
jarvis/
├── .agent/        # executable agent specification: scenarios, tests, evals, traces, fixtures
├── .claude/       # engineering memory: context, architecture, ADRs, logs, changelog
├── backend/
│   └── app/{api,core,models,schemas,llm,intelligence,tools,integrations,database}/
├── frontend/
├── docs/
├── scripts/
├── docker-compose.yml
├── .env.example
└── README.md
```

`.agent/` exactly as specified: `config/`, `prompts/`, `scenarios/`, `tests/`, `evals/{datasets,expected_outputs,scoring,reports}/`, `traces/`, `fixtures/{documents,csv,expected}/`, plus `.agent/README.md` stating the folder's contract: *"this directory answers the question 'how do we know the agent actually works?' — nothing else goes here."*

`.claude/` exactly as specified: `context/`, `architecture/`, `implementation/`, `decisions/`, `integrations/`, `api/`, `testing/`, `changes/`, `logs/`.

Seed documents written this phase:

- `.claude/context/project-overview.md` — problem statement, the one-shot-LLM gap, the closed-loop answer
- `.claude/context/member-1-scope.md` — what is mine, what is explicitly not mine (context store, knowledge base, verification internals)
- `.claude/context/architecture.md` — the modular-monolith diagram
- `.claude/context/tech-stack.md` — stack + rationale
- `.claude/context/terminology.md` — objective, intent, plan, task, tool, observation, finding, evidence, verification, gap, replan; defined once, used consistently everywhere
- `.claude/implementation/implementation-plan.md` — this file
- `.claude/decisions/ADR-001-modular-monolith.md`, `ADR-004-custom-orchestration.md` (why not LangGraph/CrewAI: control over the plan→verify→replan loop and over evaluation instrumentation *is* the contribution)
- `.claude/logs/development-log.md`, `bug-log.md`, `experiment-log.md`, `.claude/changes/changelog.md` — initialized with headers

**Acceptance**

- Every directory above exists with a README or seed file; no empty untracked dirs
- `.claude/context/terminology.md` covers all 11 core terms
- The six ADRs named in the spec exist at least in `Proposed` status

**Effort:** 1–2 sessions

---

## Phase 2 — Domain schemas (the typed spine)

**Goal:** Every object that crosses a boundary exists as a validated Pydantic v2 model before any engine is written.

**Why now:** The schemas *are* the architecture. Writing them first forces the interfaces to be designed rather than discovered.

**Build** — `backend/app/schemas/`

| Module | Types |
|---|---|
| `intent.py` | `Intent`, `RequiredOperation`, `Constraints`, `OutputFormat` |
| `objective.py` | `Objective`, `ObjectiveScope`, `SuccessCriterion` |
| `plan.py` | `Plan`, `PlanRevision`, `PlanValidationResult` |
| `task.py` | `Task`, `TaskType`, `TaskStatus`, `TaskDependency`, `TaskResult` |
| `tool.py` | `ToolDefinition`, `ToolCapability`, `ToolCall`, `ToolResult`, `ToolError` |
| `execution.py` | `ExecutionState`, `RunStatus`, `RunPhase`, `Observation` |
| `finding.py` | `Finding`, `FindingClassification`, `Confidence` |
| `evidence.py` | `Evidence`, `EvidenceRef`, `EvidenceStrength`, `EvidenceGap` |
| `verification.py` | `VerificationRequest`, `VerificationResult`, `VerificationStatus`, `VerificationIssue` |
| `event.py` | `ExecutionEvent`, `EventType` |
| `result.py` | `AgentResult`, `FinalReport`, `ReportSection` |

**Contracts** (illustrative — final signatures live in the code):

```python
class TaskStatus(str, Enum):
    PENDING = "PENDING"; READY = "READY"; RUNNING = "RUNNING"
    COMPLETED = "COMPLETED"; FAILED = "FAILED"; RETRYING = "RETRYING"
    BLOCKED = "BLOCKED"; SKIPPED = "SKIPPED"

class FindingClassification(str, Enum):
    FACT = "FACT"; INFERENCE = "INFERENCE"
    HYPOTHESIS = "HYPOTHESIS"; UNKNOWN = "UNKNOWN"

class Finding(BaseModel):
    finding_id: str
    claim: str
    classification: FindingClassification
    evidence: list[EvidenceRef]
    confidence: float = Field(ge=0.0, le=1.0)
    verification: VerificationResult | None = None
    gaps: list[EvidenceGap] = []
```

`EventType` is enumerated up front and frozen: `RUN_STARTED`, `INTENT_CREATED`, `PLAN_CREATED`, `PLAN_REVISED`, `TASK_GRAPH_CREATED`, `TASK_READY`, `TASK_STARTED`, `TASK_COMPLETED`, `TASK_FAILED`, `TASK_RETRYING`, `TOOL_SELECTED`, `TOOL_EXECUTED`, `TOOL_FAILED`, `OBSERVATION_RECORDED`, `REASONING_STARTED`, `FINDING_CREATED`, `VERIFICATION_STARTED`, `FINDING_VERIFIED`, `FINDING_REJECTED`, `EVIDENCE_GAP_DETECTED`, `REPLAN_STARTED`, `TASK_CREATED`, `REASONING_REVISED`, `VERIFICATION_COMPLETED`, `SYNTHESIS_COMPLETED`, `RUN_COMPLETED`, `RUN_FAILED`, `RUN_CANCELLED`.

**Acceptance**

- `python -c "import app.schemas"` imports cleanly with zero runtime dependency on engines
- Every enum value in the spec (8 task states, 4 classifications, all event types) is present
- Round-trip test: every model serializes to JSON and back without loss
- `mypy --strict app/schemas` clean

**Tests:** `backend/tests/unit/test_schemas.py` — validation bounds (confidence ∈ [0,1]), enum coverage, serialization round-trip.

**Docs:** `.claude/api/schemas.md`, `.claude/api/events.md`

**Effort:** 2 sessions

---

## Phase 3 — Database & persistence

**Goal:** Durable, queryable storage for runs, tasks, tool executions, findings, evidence, verifications and events.

**Why now:** Traces and evaluation need persistence from the first real run, not bolted on later.

**Build**

- `backend/app/database/session.py` — async engine, session factory, `get_session` dependency
- `backend/app/models/` — SQLAlchemy 2.0 declarative models mirroring the spec's tables: `agent_runs`, `tasks`, `task_dependencies`, `tool_executions`, `findings`, `evidence`, `verifications`, `execution_events`, plus `documents` and `document_chunks` (with a `vector(768)` column) for Phase 12
- `backend/app/database/repositories/` — one repository per aggregate (`RunRepository`, `TaskRepository`, `FindingRepository`, `EventRepository`). Engines talk to repositories, never to sessions directly.
- Alembic: `alembic/` with initial migration; `vector` extension created in migration `0001`

**Key design decisions to record**

- The event log is append-only: no updates, no deletes
- `tasks.input` / `output` are `JSONB` holding the serialized Pydantic payload, with the schema version stamped
- `findings.confidence` is `NUMERIC(4,3)` — no floating-point drift in reports
- Cascade deletes from `agent_runs` so a run can be purged atomically

**Acceptance**

- `alembic upgrade head` creates all tables on a clean database
- `alembic downgrade base` then `upgrade head` round-trips
- Repository integration tests pass against a real Postgres (test DB created/dropped per session)
- Writing 1,000 events and reading them back ordered by timestamp completes in < 2s

**Tests:** `backend/tests/integration/test_repositories.py`

**Docs:** `.claude/architecture/system-architecture.md` (persistence section); `ADR-002` and `ADR-005` move to `Accepted`

**Effort:** 2 sessions

---

## Phase 4 — LLM abstraction layer

**Goal:** One typed, swappable, instrumented door to the model — with reliable structured output from small local models.

**Why now:** Every intelligence component depends on it, and structured-output reliability is the biggest practical risk in the whole project.

**Build** — `backend/app/llm/`

```
llm/
├── provider.py      # LLMProvider protocol
├── ollama.py        # OllamaProvider
├── echo.py          # EchoProvider — deterministic fixture provider for tests/CI
├── structured.py    # generate_structured(): schema-guided call + repair loop
├── prompts.py       # prompt loader, reads .agent/prompts/*.md
└── telemetry.py     # token counts, latency, retries → ExecutionEvent
```

**Contract**

```python
class LLMProvider(Protocol):
    async def complete(self, req: CompletionRequest) -> CompletionResponse: ...
    async def embed(self, texts: list[str]) -> list[list[float]]: ...
    @property
    def model_id(self) -> str: ...
```

`generate_structured(prompt, schema: type[T], *, max_repairs=2) -> T`:

1. Call the model with the JSON schema injected and `format=json` where the provider supports it
2. Parse; on `ValidationError`, re-prompt once with the validation errors appended (the repair loop)
3. On persistent failure raise `StructuredOutputError` carrying the raw text — callers decide whether to degrade or fail the task
4. Every attempt emits telemetry: model, latency, prompt tokens, repair count

**Prompts live in `.agent/prompts/*.md`, not in Python string literals.** Prompts are versioned assets; a prompt change is a reviewable diff and is referenced by evaluation runs.

**Acceptance**

- Setting `LLM_PROVIDER=echo` runs the entire test suite with zero network calls
- `generate_structured` returns a valid model for 20/20 fixture prompts against the configured local model, with repair count recorded
- No module outside `app/llm/` imports httpx or references `OLLAMA_*` — enforced by `tests/unit/test_llm_isolation.py`

**Tests:** structured-output repair loop, timeout handling, provider swap, prompt loader missing-file error.

**Docs:** `.claude/architecture/agent-architecture.md` (LLM layer); `ADR-003` → `Accepted`

**Effort:** 2 sessions

---

## Phase 5 — Event bus & execution trace

**Goal:** A single `emit()` path that every component uses, producing the timeline that powers the UI, the traces and the evaluation.

**Why now:** If tracing is added after the engines, coverage will be patchy and the "fully traceable" claim will not hold.

**Build** — `backend/app/core/events.py`

- `EventBus` with in-process async subscribers
- Subscribers: `DatabaseEventSink` (persists), `StreamEventSink` (feeds SSE in Phase 19), `TraceFileSink` (writes `.agent/traces/*.json` when `TRACE_TO_FILE=1`)
- `run_clock`: every event carries `t_offset_ms` relative to `RUN_STARTED` — this is what produces the `00:00.420 INTENT_CREATED` style timeline
- Redaction hook: event payloads pass through a filter that strips model deliberation text before persisting — the mechanism behind invariant #3

**Acceptance**

- A run produces a monotonically ordered event list with no gaps in `t_offset_ms`
- `.agent/traces/sample_success.json` is generated by a real run, not authored by hand
- A trace can be replayed into the timeline renderer and reproduce the run's phase sequence

**Tests:** ordering under concurrent emitters; sink failure isolation (a failing sink must not kill a run).

**Docs:** `.claude/api/events.md`

**Effort:** 1 session

---

# STAGE B — COGNITION CORE (Phases 6–11)

## Phase 6 — Intent engine

**Goal:** Turn ambiguous natural-language objectives into a validated `Intent` with required operations and constraints.

**Build** — `backend/app/intelligence/intent/`

- `engine.py` — `IntentEngine.analyze(objective_text, attachments) -> Intent`
- `.agent/prompts/intent.md` — the prompt asset
- `validators.py` — required operations must be drawn from a known operation vocabulary; unknown operations are either mapped or flagged `UNSUPPORTED_OPERATION` rather than silently dropped
- `heuristics.py` — deterministic pre-pass: detect attached file types, detect comparison/contradiction keywords, so the model is never the only signal

**Output shape** matches the spec exactly: `goal`, `objective`, `required_operations[]`, `constraints{evidence_required, max_runtime_s, ...}`, `output_format`.

**Acceptance**

- 10 fixture objectives in `.agent/tests/test_intent.yaml` produce intents matching the expected `goal` and containing the expected operations (set overlap ≥ 0.8)
- An ambiguous objective ("look at these files") yields an intent with `clarification_needed: true` rather than a hallucinated plan
- Adversarial input (prompt injection inside an attached document) does not alter the intent — injected instructions in documents are treated as data

**Tests:** `.agent/tests/test_intent.yaml` + `backend/tests/unit/test_intent_engine.py`

**Docs:** `.claude/implementation/phase-02-intent.md`

**Effort:** 2 sessions

---

## Phase 7 — Planner → validated DAG

**Goal:** Generate a candidate decomposition with the model, then **validate and repair it into a legal DAG in application code**.

**Why this split matters:** the model proposes; the system disposes. Plan validity must be a property of the system, not a hope about the model. This is the difference between "an LLM wrote some steps" and "the agent produces a valid executable plan."

**Build** — `backend/app/intelligence/planner/`

- `engine.py` — `Planner.create_plan(intent, available_tools, context) -> Plan`
- `.agent/prompts/planner.md` — includes the tool catalogue so the model plans against real capabilities
- `validator.py` — the hard part:
  - every `depends_on` references an existing task id
  - no cycles (DFS with colouring; report the offending path)
  - no orphan tasks that nothing consumes and that produce nothing terminal
  - every `required_operation` from the intent is covered by ≥ 1 task; uncovered operations trigger a bounded re-prompt
  - task types are drawn from the registered `TaskType` vocabulary
  - plan size guard: `2 ≤ tasks ≤ MAX_PLAN_TASKS` (default 20)
- `repair.py` — deterministic fixes before re-prompting: drop duplicate edges, break trivial self-loops, topologically reorder ids
- `PlanValidationResult` records every violation and every repair, and both are persisted — this is evaluation evidence

**Acceptance**

- Planner output for the reference audit scenario matches the expected shape: document processing fans out to extraction tasks, which converge on comparison, then detection, evidence retrieval, verification, synthesis
- Injected malformed plans (cycle, dangling dependency, empty task list) are all caught by the validator with a specific error code — 100% detection on the 8 fixture malformed plans
- Re-prompting on validation failure is capped at 2 attempts, after which the run fails cleanly with `PLAN_INVALID` rather than executing garbage

**Tests:** `.agent/tests/test_planner.yaml`, `backend/tests/unit/test_plan_validator.py` (cycle detection is its own test class)

**Docs:** `.claude/architecture/task-graph.md`, `.claude/implementation/phase-03-planner.md`, `ADR-006-task-graph.md`

**Effort:** 3 sessions

---

## Phase 8 — Task graph engine

**Goal:** A live, mutable dependency graph with correct state semantics — the substrate replanning will later edit.

**Build** — `backend/app/intelligence/graph/`

- `task_graph.py` — `TaskGraph` with `add_task`, `add_dependency`, `ready_tasks()`, `mark(task_id, status)`, `block_descendants`, `to_dict`/`from_dict`
- `transitions.py` — an explicit state machine; illegal transitions raise rather than silently pass:

```
PENDING → READY → RUNNING → COMPLETED
                    ↓
                  FAILED → RETRYING → RUNNING
                    ↓
                  BLOCKED (descendants of a terminal failure)
                  SKIPPED (made unnecessary by replanning)
```

- `mutation.py` — `insert_task_before/after`, `replace_subgraph`, `invalidate_downstream` — the API Phase 16 uses. Every mutation is versioned: the graph keeps a `revision` counter and an append-only mutation log.

**Acceptance**

- `ready_tasks()` returns exactly the tasks whose dependencies are all `COMPLETED`
- A failed task with `retries_remaining == 0` blocks its transitive descendants and nothing else
- Mid-execution insertion of a task keeps the graph acyclic (validated after every mutation)
- The graph survives serialize → deserialize with identical readiness behaviour

**Tests:** `.agent/tests/test_execution.yaml` (graph section) plus property-style tests on random DAGs: readiness is never granted to a task with an incomplete ancestor.

**Docs:** `.claude/architecture/task-graph.md`, `.claude/implementation/phase-04-task-graph.md`

**Effort:** 2 sessions

---

## Phase 9 — Tool system & registry · **Milestone M1**

**Goal:** Dynamically registered, schema-described capabilities — and the first end-to-end vertical slice.

**Build** — `backend/app/tools/`

```
tools/
├── base.py          # Tool ABC: name, description, input_schema, output_schema, capabilities, execute()
├── registry.py      # decorator-based registration, catalogue export for prompts
├── document_search.py
├── document_extract.py     # PDF/text extraction
├── csv_analysis.py
├── calculator.py           # safe expression evaluation — AST whitelist, NO eval()
├── evidence_retrieval.py
├── context_retrieval.py    # M2Context adapter (local fallback until integrated)
├── knowledge_search.py     # Member 3 adapter (local fallback)
└── verification_tool.py    # Member 4 adapter (local baseline until integrated)
```

**Tool contract**

```python
class Tool(ABC):
    name: str
    description: str
    capabilities: set[ToolCapability]
    input_schema: type[BaseModel]
    output_schema: type[BaseModel]
    cost_hint: CostHint          # used by Phase 17
    async def execute(self, call: ToolCall, ctx: ToolContext) -> ToolResult: ...
```

**Security note:** `CalculatorTool` parses with `ast.parse` and walks a whitelist of node types. No `eval`, no `exec`, no dynamic import — this directly satisfies the "no arbitrary code execution" rule.

**M1 — Vertical slice (the phase's real deliverable):**

```
"Analyze these two project reports and find inconsistencies."
   → Intent → Plan → TaskGraph → DocumentExtractTool ×2
   → naive reasoning stub → Finding + Evidence → Result
```

Run end to end from a CLI entry point: `python -m app.cli run --objective "..." --docs .agent/fixtures/documents/`. Real documents, real model, real DAG, real tool calls. The reasoning stub is honest and labelled — it becomes Phase 13.

**Acceptance**

- `registry.catalogue()` produces the tool list injected into the planner prompt
- The slice produces a non-empty `AgentResult` with ≥ 1 finding carrying ≥ 1 evidence reference pointing at a real document location
- A full event trace is written to `.agent/traces/sample_success.json`
- Calculator rejects `__import__("os").system("...")` with `UnsafeExpressionError`

**Docs:** `.claude/architecture/tool-system.md`, `.claude/implementation/phase-05-tools.md`

**Effort:** 3 sessions

---

## Phase 10 — Tool router

**Goal:** Decide which registered capability accomplishes a given task — defensibly, with a recorded reason.

**Build** — `backend/app/intelligence/router/`

- `engine.py` — three-stage routing:
  1. **Capability filter** (deterministic): task type + required capabilities → candidate set
  2. **Schema compatibility** (deterministic): can the task's inputs satisfy the tool's `input_schema`?
  3. **LLM tiebreak** (only when ≥ 2 candidates remain): `.agent/prompts/router.md` picks and justifies
- `ToolSelection` records `tool_name`, `alternatives_considered`, `reason`, `selection_mode` (`DETERMINISTIC` | `LLM_TIEBREAK` | `FALLBACK`), `confidence`
- `fallbacks.py` — ordered fallback chains per capability, used by Phase 11 on tool failure

**Why deterministic-first:** routing accuracy becomes measurable and mostly model-independent, so the evaluation metric "tool selection accuracy" measures something real.

**Acceptance**

- 20 routing fixtures in `.agent/tests/test_router.yaml` — target ≥ 90% correct tool, 100% correct *capability class*
- When no tool can serve a task, the router returns `NoCapableToolError` and the task is marked `SKIPPED` with a reason, not silently dropped
- Every selection emits `TOOL_SELECTED` with its reason

**Docs:** `.claude/implementation/phase-06-execution.md` (routing section)

**Effort:** 2 sessions

---

## Phase 11 — Execution engine · **Milestone M2**

**Goal:** Dependency-aware, concurrent, fault-tolerant execution of the task graph.

**Build** — `backend/app/intelligence/execution/`

- `engine.py` — the scheduler loop:

```python
while graph.has_runnable_work() and not cancelled:
    ready = graph.ready_tasks()
    batch = ready[:MAX_PARALLEL_TASKS]
    results = await asyncio.gather(*(run_task(t) for t in batch), return_exceptions=True)
    for r in results:
        observe(r); graph.mark(...)
```

- `task_runner.py` — per task: route → build `ToolCall` → execute with timeout → capture `Observation` → persist a `tool_executions` row
- `retry.py` — exponential backoff, `MAX_TASK_RETRIES`, distinguishing **transient** failures (timeout, connection) from **permanent** ones (schema violation, missing input); only transient failures retry
- `fallback.py` — on permanent tool failure, try the next tool in the router's fallback chain, then degrade to `SKIPPED` plus a recorded `EvidenceGap`
- `cancellation.py` — cooperative cancellation token, honoured between tasks and inside long tool calls
- `budget.py` — enforces `MAX_TOOL_CALLS_PER_RUN` and a wall-clock ceiling

**Acceptance**

- **Demo 2 (parallel execution):** a plan with 3 independent extraction tasks shows overlapping `TASK_STARTED`/`TASK_COMPLETED` intervals in the trace, and wall-clock < 0.6 × serial time
- **Demo 4 (failure recovery):** `.agent/scenarios/failed_tool.yaml` injects a failing tool; the trace shows `TOOL_FAILED → TASK_RETRYING → fallback tool → TASK_COMPLETED`, and the run completes
- Cancelling a run mid-flight leaves the DB consistent: run `CANCELLED`, in-flight tasks `FAILED` with reason `CANCELLED`, no orphaned `RUNNING` rows
- No task ever executes before all its dependencies are `COMPLETED` (asserted in the runner, not just the graph)

**Tests:** `.agent/scenarios/failed_tool.yaml`, `basic_investigation.yaml`; `backend/tests/integration/test_execution_engine.py`

**Docs:** `.claude/implementation/phase-06-execution.md`

**Effort:** 3 sessions

---

# STAGE C — THE DIFFERENTIATORS (Phases 12–18)

## Phase 12 — Context manager & retrieval

**Goal:** A working memory that keeps the run's accumulated state coherent and retrievable, without stuffing everything into every prompt.

**Build** — `backend/app/intelligence/context/`

- `manager.py` — `ContextManager` holds the `ExecutionState` and exposes `snapshot_for(component)`, returning only what that component needs (intent + plan for the planner; observations + evidence for reasoning)
- `compaction.py` — when accumulated observations exceed a token budget, compact older observations into summaries while keeping all evidence references intact. **Evidence pointers are never compacted away** — a summary that loses its source is worthless here.
- `retrieval.py` — pgvector semantic search over ingested document chunks: `search(query, k, filters) -> list[Chunk]` with source and location metadata
- `ingest.py` — document → chunks → embeddings → `document_chunks`, preserving page/row locators so evidence can cite `doc_A:p12`
- `integrations/m2context.py` — adapter to Member 2's context service behind a `ContextProvider` protocol; the local pgvector implementation is the default and the fallback

**Acceptance**

- Retrieval returns chunks with exact source locators (`document_id`, `page`/`row`, `char_span`)
- Compaction under a forced small budget preserves 100% of evidence references
- Swapping the context provider (local ↔ M2Context) requires no change outside `integrations/`

**Docs:** `.claude/integrations/m2context.md`, `.claude/architecture/reasoning-engine.md` (context section)

**Effort:** 2 sessions

---

## Phase 13 — Reasoning engine

**Goal:** Turn observations into **structured, classified, evidence-bound findings** — not prose.

**Build** — `backend/app/intelligence/reasoning/`

- `engine.py` — `ReasoningEngine.derive_findings(state) -> list[Finding]`
- `.agent/prompts/reasoning.md` — instructs the model to emit candidate claims with explicit source citations and a self-assessed classification
- `binder.py` — **the critical component**: every claim's cited source is resolved against actually retrieved chunks. A citation that cannot be resolved is not an error to hide — the claim keeps the citation but the evidence is marked `UNRESOLVED`, which feeds Phase 14 and the hallucination metric directly.
- `classifier.py` — post-hoc classification rules layered over the model's self-report:
  - `FACT` — every element of the claim traces to resolved evidence
  - `INFERENCE` — the claim combines ≥ 2 resolved sources with a stated reasoning step
  - `HYPOTHESIS` — partially supported; at least one element unresolved
  - `UNKNOWN` — no resolved evidence
- `confidence.py` — confidence is **computed**, not asked for: `f(evidence_strength, source_agreement, resolution_rate, classification)`. A model-declared 0.96 with unresolved evidence cannot survive.

**This is where the "evidence-first" claim is earned.** The model can say anything; the binder decides what counts.

**Acceptance**

- On the contradiction fixture, the engine produces ≥ 3 findings, each with resolvable evidence refs
- A deliberately unsupported claim injected into the model output is classified `UNKNOWN`/`HYPOTHESIS` with confidence < 0.4 — never `FACT`
- Evidence coverage (fraction of findings with ≥ 1 resolved evidence ref) ≥ 0.9 on fixtures
- Confidence values are reproducible given the same evidence set (pure function, unit-tested)

**Tests:** `.agent/tests/test_reasoning.yaml`, `.agent/scenarios/contradiction_detection.yaml`

**Docs:** `.claude/architecture/reasoning-engine.md`, `.claude/implementation/phase-07-reasoning.md`

**Effort:** 3 sessions

---

## Phase 14 — Evidence gap detector · **Milestone M3 (headline feature #1)**

**Goal:** When support is insufficient, name *what specific evidence is missing* and turn that into an executable task.

**Why this is the centrepiece:** the interesting behaviour is not "I'm not sure." It is *"I am missing the approved baseline schedule; retrieving it would resolve this claim."*

**Build** — `backend/app/intelligence/evidence_gap/`

- `detector.py` — `detect(finding, state) -> list[EvidenceGap]`
- `decomposer.py` — decomposes a claim into its **verifiable elements** (entities, quantities, dates, relations). This is the mechanism that makes gaps specific: element-level support is checked, so the gap is "the baseline completion date", not "more evidence".
- `gap_types.py` — `MISSING_SOURCE`, `MISSING_BASELINE`, `UNRESOLVED_CITATION`, `CONFLICTING_SOURCES`, `INSUFFICIENT_GRANULARITY`, `STALE_SOURCE`
- `task_proposal.py` — each gap maps to a proposed task with a concrete query:

```
EvidenceGap(type=MISSING_BASELINE, element="approved baseline completion date")
    → Task(type=EVIDENCE_RETRIEVAL,
           tool_hint="document_search",
           input={"query": "approved baseline schedule completion date",
                  "scope": ["project_report.pdf", "milestone_report.pdf"]})
```

- `.agent/prompts/evidence_gap.md` — used only for phrasing the retrieval query, never for deciding whether a gap exists (that is deterministic, from element resolution)

**Acceptance**

- **Demo 3:** `.agent/scenarios/evidence_gap.yaml` — a finding with partial support produces a typed gap, a proposed task with a concrete query, and a trace showing `EVIDENCE_GAP_DETECTED` with the named missing element
- Gap detection is deterministic given the same finding + evidence set
- False-gap rate on fully supported fixture findings ≤ 10%
- Every gap carries a human-readable `missing` string suitable for direct display in the UI

**Tests:** `.agent/tests/test_evidence_gap.yaml`, `.agent/scenarios/evidence_gap.yaml`

**Docs:** `.claude/implementation/evidence-gap.md`, update `.claude/architecture/reasoning-engine.md`, ADR if the element-decomposition approach changes

**Effort:** 3 sessions

---

## Phase 15 — Verification integration

**Goal:** An independent check on findings, integrated through a provider boundary so Member 4's work drops in without refactoring.

**Build** — `backend/app/integrations/verification.py`

```python
class VerificationProvider(Protocol):
    async def verify(self, req: VerificationRequest) -> VerificationResult: ...
```

- `BaselineVerifier` (Member 1's own, always available): re-checks each claim element against the cited evidence *independently of the reasoning pass* — a separate prompt with only the claim and the evidence text, no access to the reasoning trail. Returns `SUPPORTED` / `PARTIALLY_SUPPORTED` / `UNSUPPORTED` / `CONTRADICTED` with issues.
- `RemoteVerifier` — HTTP adapter for Member 4's service, selected by the `VERIFICATION_PROVIDER` env var, with timeout and fallback to baseline
- `.agent/prompts/verification.md`
- Verification results persist to `verifications` and emit `FINDING_VERIFIED` / `FINDING_REJECTED`

**Contract with Member 4** (documented and frozen at this phase): request `{claim, evidence[], context_hints}` → response `{status, confidence, issues[]}`.

**Acceptance**

- A finding whose evidence contradicts it is returned `CONTRADICTED`, not `SUPPORTED` — tested with 6 adversarial fixtures
- Swapping the provider changes no code outside `integrations/`
- A remote verifier timeout degrades to baseline and records `VERIFICATION_DEGRADED` — verification is never silently dropped

**Docs:** `.claude/integrations/member-4-verification.md`, `.claude/architecture/verification-loop.md`, `.claude/implementation/phase-08-verification.md`

**Effort:** 2 sessions

---

## Phase 16 — Adaptive replanning loop · **Milestone M4 (headline feature #2)**

**Goal:** Close the loop — the plan is not sacred; unsupported findings and new information change the graph mid-run.

**Build** — `backend/app/intelligence/replanning/`

- `controller.py` — the loop:

```
reason → verify → for each unsupported/partial finding:
    gaps = detect_gaps(finding)
    actions = propose_tasks(gaps)
    selected = select(actions)            # Phase 17 scores these
    graph.insert(selected)                # versioned mutation
    execute(selected)
    re-reason(affected findings only)     # scoped, not a full re-run
    re-verify
until all resolved or iteration == MAX_REPLAN_ITERATIONS
```

- `triggers.py` — replanning fires on: an unsupported finding with an actionable gap · a permanent task failure with a viable alternative path · new information that invalidates a plan assumption · a contradiction between sources requiring a tiebreak source
- `scoped_reasoning.py` — only findings touching new evidence are re-derived. Full re-reasoning on each iteration is wasteful and makes the loop unconvincing.
- `termination.py` — stop conditions, each recorded with a reason: `RESOLVED`, `MAX_ITERATIONS`, `NO_ACTIONABLE_GAP`, `BUDGET_EXHAUSTED`, `DIMINISHING_RETURNS` (confidence gain < ε across an iteration)
- Every iteration writes a `PlanRevision` — the plan's history is queryable and displayable

**Acceptance**

- **Demo 5:** `.agent/scenarios/replanning.yaml` — initial plan, new information invalidates an assumption, the graph is revised, execution continues, and the final findings differ measurably from the pre-replan set
- **Demo 3 end-to-end:** partially supported finding → gap → new task → evidence retrieved → re-verified as `SUPPORTED`, all visible in the trace
- The loop provably terminates: a scenario where evidence is genuinely unavailable stops at `MAX_REPLAN_ITERATIONS` with the finding honestly reported as unresolved, not silently promoted
- Replan iterations never exceed the configured ceiling under any fixture, including adversarial ones

**Tests:** `.agent/scenarios/replanning.yaml`, `.agent/tests/test_replanning.yaml`, plus a stress fixture that would loop forever without termination logic

**Docs:** `.claude/architecture/verification-loop.md`, `.claude/implementation/phase-09-replanning.md`

**Effort:** 3 sessions

---

## Phase 17 — Cost-aware action selection

**Goal:** When several actions could close a gap, pick the one with the best expected information gain per unit cost.

**Scope discipline:** heuristic, transparent, and honest about being heuristic. No pretence of decision-theoretic optimality.

**Build** — `backend/app/intelligence/planning_policy/`

- `scoring.py`:

```
score = (expected_information_gain × gap_severity) / (estimated_cost + ε)

expected_information_gain  ← gap-type prior × source-match score from retrieval
estimated_cost             ← tool.cost_hint × input size × expected latency
gap_severity               ← confidence deficit of the affected finding
```

- `policy.py` — selects the top-k actions per replan iteration under the remaining budget
- Every selection persists its score breakdown — this is what makes the claim inspectable rather than decorative

**Acceptance**

- Given a cheap 2-document search and an expensive 20-document scan with comparable expected gain, the policy selects the cheap one and records why
- Disabling the policy (`PLANNING_POLICY=naive`) still runs, enabling an A/B evaluation of tasks executed per resolved finding
- Recorded in `.claude/logs/experiment-log.md` as Experiment 002 with measured before/after task counts

**Docs:** `.claude/architecture/agent-architecture.md` (policy section), `ADR-007-cost-aware-policy.md`

**Effort:** 2 sessions

---

## Phase 18 — Synthesis & final report

**Goal:** A structured, evidence-backed report — the artifact the user actually reads.

**Build** — `backend/app/intelligence/synthesis/`

- `engine.py` — assembles `FinalReport` from state; the model writes prose **only** inside sections whose facts are already fixed. Numbers, confidences and evidence refs are injected programmatically, never regenerated by the model.
- `.agent/prompts/synthesis.md`
- Sections, exactly as specified: Executive Summary · Investigation Scope · Execution Summary · Verified Findings · Evidence · Uncertain Findings · Rejected Findings · Reasoning · Actions Performed · Confidence · Limitations
- `renderers/` — `markdown.py`, `json.py` (the API shape consumed by the frontend)

**Acceptance**

- Every claim in the report body carries an evidence reference or appears under Uncertain/Rejected
- **Rejected findings are shown, not hidden** — a report that only shows what survived is not an audit
- The Limitations section is generated from real run facts: skipped tasks, unresolved gaps, degraded verification, budget exhaustion
- The report regenerates identically from a stored run (pure function of persisted state)

**Tests:** golden-file comparison on the reference scenario, with model-written prose excluded from the diff.

**Docs:** `.claude/implementation/phase-10-synthesis.md`

**Effort:** 2 sessions

---

# STAGE D — SURFACE (Phases 19–22)

## Phase 19 — FastAPI + SSE streaming · **Milestone M5**

**Goal:** The engine is reachable over HTTP and streams its execution live.

**Build** — `backend/app/api/v1/`

| Method | Route | Purpose |
|---|---|---|
| POST | `/api/v1/missions` | Create + start a mission (objective + document refs) |
| GET | `/api/v1/missions` | List missions |
| GET | `/api/v1/missions/{id}` | Mission detail + current phase |
| GET | `/api/v1/missions/{id}/tasks` | Task graph (nodes + edges + statuses) |
| GET | `/api/v1/missions/{id}/events` | Full event log (paginated) |
| GET | `/api/v1/missions/{id}/findings` | Findings + evidence + verification |
| GET | `/api/v1/missions/{id}/report` | Final report (JSON / Markdown) |
| POST | `/api/v1/missions/{id}/cancel` | Cooperative cancellation |
| GET | `/api/v1/missions/{id}/stream` | **SSE** live execution events |
| POST | `/api/v1/documents` | Upload documents for a mission |

- SSE chosen over WebSocket: the frontend needs one-way execution updates, and SSE gives reconnect-and-replay from `Last-Event-ID` for free. Recorded as `ADR-008-sse-over-websocket.md`.
- Missions run as background tasks with a run registry; the API never blocks on a run
- Error contract: every 4xx/5xx returns `{error_code, message, run_id?, details?}` — the frontend renders codes, not raw strings

**Acceptance**

- `curl -N /stream` shows events arriving live during a real run, in order, with `t_offset_ms`
- Reconnecting with `Last-Event-ID` replays missed events with no duplicates and no gaps
- Cancel returns 202 and the run reaches `CANCELLED` within one task boundary
- OpenAPI schema generated and committed to `docs/openapi.json`

**Docs:** `.claude/api/endpoints.md`, `.claude/implementation/phase-09-api.md`

**Effort:** 3 sessions

---

## Phase 20 — Agent evaluation harness

**Goal:** Prove the agent works — with numbers the system computes, on a dataset that lives in the repo.

**Why it sits here:** the full pipeline must exist before end-to-end metrics mean anything, but this precedes the UI in priority. The evaluation harness is a bigger part of the contribution than the frontend.

**Build** — `.agent/evals/` + `backend/app/evaluation/`

- `runner.py` — executes every scenario in `.agent/evals/datasets/` against a pinned model + prompt version, writing `.agent/evals/reports/<timestamp>-<model>.json` and a Markdown summary
- `scoring/` — one scorer per metric:

| Metric | Definition |
|---|---|
| Intent accuracy | Operation-set F1 vs. expected intent |
| Plan validity | % of plans passing the validator with zero repairs |
| Dependency correctness | Edge-level precision/recall vs. expected DAG |
| Tool selection accuracy | % of tasks routed to the expected tool (and capability class) |
| Evidence coverage | % of findings with ≥ 1 resolved evidence ref |
| Verification success | % of candidate findings surviving independent verification |
| Replanning success | % of detected gaps closed within the iteration ceiling |
| Unsupported claim rate | % of report claims with no resolved evidence — the hallucination proxy |
| Task efficiency | executed tasks ÷ minimal sufficient tasks (expected plan) |
| Latency | wall-clock per run, and per phase |

- `datasets/` — ≥ 20 scenarios: basic investigation, contradiction detection, evidence gap, tool failure, replanning, complex multi-document, plus negative cases (no contradiction exists — the agent must *not* invent one)
- `expected_outputs/` — expected intents, expected DAG edge sets, expected findings (claim-level, fuzzy-matched)
- `regression.py` — compares against the last committed report and fails on regression beyond tolerance

**Acceptance**

- `python -m app.evaluation.run --suite all` produces a report with every metric populated by computation
- A deliberately broken planner drops plan-validity in the report — the harness detects real regressions
- Negative-case scenarios score high on "no fabricated findings"
- Two models compared and written up as Experiment 001 in `.claude/logs/experiment-log.md`

**Docs:** `.claude/testing/agent-evaluation.md`, `.claude/testing/regression-testing.md`

**Effort:** 3 sessions

---

## Phase 21 — Frontend: JARVIS Mission Control

**Goal:** An operations console, not a chat window.

**Build** — `frontend/` (React + TypeScript + Vite + Tailwind + React Query + Zustand + Recharts + Framer Motion)

```
src/
├── pages/{MissionList,NewMission,MissionDetail,Evaluation}.tsx
├── components/
│   ├── mission/{PhaseTracker,ObjectiveInput,DocumentUpload}.tsx
│   ├── graph/{TaskGraph,TaskNode,GraphLegend}.tsx
│   ├── evidence/{FindingCard,EvidencePanel,ConfidenceBar,VerificationBadge}.tsx
│   ├── trace/{EventTimeline,EventRow}.tsx
│   └── report/{FinalReport,ReportSection}.tsx
├── hooks/{useMission,useMissionStream,useTaskGraph}.ts
├── stores/missionStore.ts
└── services/api.ts        # generated types from docs/openapi.json
```

**Design rules**

- The landing view is a mission list plus "New Mission", never a chat transcript
- Phase tracker across the top: Understanding · Planning · Executing · Reasoning · Verifying · Replanning · Synthesizing
- Findings always render claim + classification + confidence + verification state + expandable evidence with source locator
- Uncertainty is visible, not smoothed: distinct treatment for verified / uncertain / rejected
- No exposure of model deliberation — only operational events

**Acceptance**

- Creating a mission from the UI starts a real run and lands on the detail page
- The report page renders all 11 sections with working evidence drill-down
- Accessible colour contrast; the confidence encoding does not rely on colour alone

**Effort:** 3 sessions

---

## Phase 22 — Live execution visualization

**Goal:** Watch the agent work in operational terms — the moment that sells the project.

**Build**

- `useMissionStream` — SSE subscription, reconnect with `Last-Event-ID`, event-sourced store updates
- Animated task graph: nodes transition PENDING → READY → RUNNING → COMPLETED/FAILED with Framer Motion; tasks inserted by replanning **animate in** and are visibly marked as replan-generated
- The evidence-gap moment: when `EVIDENCE_GAP_DETECTED` arrives, the affected finding card shows the named missing element and the spawned retrieval task
- Timeline panel rendering the `00:00.420 INTENT_CREATED` trace live
- Evaluation dashboard (Recharts): metric trends across committed eval reports
- Trace replay mode: load any `.agent/traces/*.json` and replay it at speed — presentation insurance against a live model failing on stage

**Acceptance**

- A full run is watchable end to end with no page refresh
- Replan insertion is visually obvious — a viewer can point at the moment the plan changed
- Replay of a stored trace is visually identical to a live run
- Reconnecting mid-run recovers without duplicated or missing events

**Docs:** `.claude/architecture/integrations.md` (frontend contract)

**Effort:** 3 sessions

---

# STAGE E — PROOF (Phases 23–24)

## Phase 23 — Test hardening & CI

**Goal:** The system is defensible under questioning, and regressions are caught automatically.

**Build**

- Unit coverage target ≥ 80% on `app/intelligence/**` and `app/schemas/**`
- Integration suite against real Postgres, with `EchoProvider` for determinism
- Agent scenario suite runnable in CI (echo provider) and locally (real model)
- Adversarial suite: prompt injection inside documents · malformed plans · contradictory sources · empty/corrupt documents · zero-finding runs · tool timeout storms
- GitHub Actions: lint (ruff) → types (mypy) → unit → integration (Postgres service) → agent scenarios → eval regression check
- `pytest-randomly` to catch order-dependent tests

**Acceptance**

- CI green on a clean clone
- Full suite < 5 minutes with the echo provider
- Every "must not do" item from the spec has a test that would fail if it were violated (LLM isolation, no `eval`, no chain-of-thought in persisted events, bounded loops)

**Docs:** `.claude/testing/testing-strategy.md`, `unit-tests.md`, `integration-tests.md`

**Effort:** 2 sessions

---

## Phase 24 — Documentation & demo package

**Goal:** Someone else can run it, and you can present it in ten minutes without luck being involved.

**Build**

- `README.md` — problem, architecture diagram, quickstart, demo script
- `.claude` completed: all ADRs `Accepted`, all architecture docs matching the built system, changelog and development log current
- `docs/demo-script.md` — the six demos, each with its exact command, expected trace, and fallback recorded trace:

| Demo | Shows | Scenario file |
|---|---|---|
| 1 Basic investigation | objective → intent → plan → execute → result | `basic_investigation.yaml` |
| 2 Parallel execution | fan-out, concurrent execution, convergence | `basic_investigation.yaml` (timing view) |
| 3 Evidence gap | gap detected → task created → evidence found → verified | `evidence_gap.yaml` |
| 4 Failure recovery | tool fails → retry → fallback → continue | `failed_tool.yaml` |
| 5 Replanning | plan invalidated → graph revised → execution continues | `replanning.yaml` |
| 6 Confidence | finding → evidence → confidence → verification → status | `contradiction_detection.yaml` |

- A fresh evaluation report committed as the presented numbers, stamped with model and prompt version
- A one-page contribution statement for the panel, tied to specific files and metrics

**Acceptance**

- A clean clone reaches a completed demo run following only the README
- Every demo has a recorded trace fallback
- No metric shown anywhere is hard-coded

**Effort:** 2 sessions

---

## 3. Integration contracts (frozen early, implemented late)

These are written in Phase 2 and stubbed with local fallbacks, so Member 1 is never blocked by another member's timeline.

| Member | Protocol | Local fallback | Doc |
|---|---|---|---|
| M2 — Context | `ContextProvider.retrieve(query, scope, k)` | pgvector retrieval (Phase 12) | `.claude/integrations/m2context.md` |
| M3 — Knowledge | `KnowledgeProvider.search(query, filters)` | local document index | `.claude/integrations/member-3-knowledge.md` |
| M4 — Verification | `VerificationProvider.verify(claim, evidence)` | `BaselineVerifier` (Phase 15) | `.claude/integrations/member-4-verification.md` |

Rule: **never import another member's implementation directly.** Selection is by environment variable; every provider has a timeout and a documented degradation path.

---

## 4. Risk register

| Risk | Impact | Mitigation | Phase |
|---|---|---|---|
| Local model produces invalid JSON | Blocks every component | Repair loop + schema injection + `EchoProvider` for CI | 4 |
| Planner emits invalid DAGs | Unexecutable plans | Validation + deterministic repair + bounded re-prompt + clean `PLAN_INVALID` failure | 7 |
| Replan loop fails to terminate | Runaway cost | Hard ceiling + diminishing-returns stop + budget guard | 16 |
| Model-declared confidence is meaningless | Undermines the whole evidence story | Confidence computed from resolved evidence, not asked for | 13 |
| Ollama unavailable on this machine | Development stalls | Provider abstraction + echo provider + recorded traces | 0, 4 |
| Scope creep into other members' areas | Late, unfocused MVP | `member-1-scope.md` is the boundary; providers only | 1 |
| Demo depends on live model behaviour | Presentation risk | Trace replay mode | 22, 24 |
| Prompt injection via uploaded documents | Hijacked agent | Document content is data; injection fixtures in the adversarial suite | 6, 23 |

---

## 5. Minimum defensible MVP

If time runs short, this is the cut line. Phases **0–16, 18, 19, 20** plus a reduced Phase 21 (mission detail + report only, no animated graph) still deliver the full contribution claim: objective → intent → validated DAG → routed tools → concurrent execution → evidence-bound findings → gap detection → verification → adaptive replanning → report, with computed evaluation metrics.

Phases 17, 22 and parts of 21 are the polish that makes it land well. They are not the argument.

---

## 6. Session protocol

Every implementation session follows the working rule:

1. Inspect repository state
2. Read the relevant `.claude` context
3. Confirm current architecture against the docs
4. Identify the required change (name the phase)
5. Implement
6. Run `pytest`
7. Run the relevant `.agent` scenarios/evals
8. Record results
9. Update architecture/implementation docs
10. Update `changelog.md`
11. Update `development-log.md`
12. Report files changed
13. Report tests executed
14. Report known issues

No undocumented architectural changes. Ever.
