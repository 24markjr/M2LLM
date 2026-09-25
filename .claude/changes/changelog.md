# Changelog

All notable changes to JARVIS (Member 1 — intelligence & agent orchestration).
Newest first. Categories: Added · Changed · Fixed · Removed · Known Issues.

---

## 2026-09-23 - Phase 6: Intent engine

### Added

- `app/intelligence/intent/engine.py` - `IntentEngine`, the deterministic pre-pass
  (`derive_operations`), operation mapping onto the closed vocabulary, and ambiguity
  detection
- `.agent/prompts/intent.md` - the first prompt asset (version 1)
- `app/cli.py` - `python -m app.cli intent "..."` and `health`; prints the objective,
  the pre-pass, the execution trace and the structured intent
- `backend/tests/unit/test_intent.py` - 24 tests, all on `EchoProvider`
- `docs/demo-script.md`

### Design

- **The model proposes operations as free text; the system maps them.** Constraining the
  model to an enum produces a silent nearest-match; mapping afterwards makes an
  out-of-vocabulary request visible as `UnsupportedOperation` instead of quietly dropped.
- **A deterministic pre-pass runs before the model**, from keywords and file types, so the
  model is never the only signal and the engine degrades to something usable if it fails.
- **Ambiguity is a valid answer.** "Look at these files" yields `clarification_needed`,
  not a confident plan.

### Measured (qwen3:4b, warm)

- Clear objective -> 14 operations, 0 repair attempts, ~3.2 s
- First call after boot ~36 s (one-time VRAM load)

### Changed

- `pyproject.toml` - `app/cli.py` exempted from the `T20` print rule

### Verified

- `pytest -m "not llm"` - 196 passed
- `mypy --strict` - clean, 36 files
- `ruff check` + `format --check` - clean

---

## 2026-09-23 — Phases 4 & 5: LLM abstraction and the event bus

### Added

- `backend/app/llm/` — the only door to a language model (invariant #1)
  - `provider.py` — `LLMProvider` protocol, `CompletionRequest/Response`, `EmbeddingResponse`
  - `ollama.py` — local inference; the only module in the project that speaks HTTP to a model
  - `echo.py` — deterministic fixture provider, plus opt-in JSON-Schema synthesis
  - `structured.py` — `generate_structured()` with the validation-error repair loop
  - `prompts.py` — `PromptLibrary` loading versioned assets from `.agent/prompts/`
  - `telemetry.py` — repair counts, latency and tokens; emits `LLM_CALL_COMPLETED`
  - `errors.py` — typed failures carrying a `FailureClass`
- `backend/app/core/events.py` — `EventBus`, `RunClock`, `RunEventEmitter`, and the
  `Memory`/`Stream`/`TraceFile` sinks
- `backend/app/core/agent_config.py` — the `.agent/config/*.yaml` loader with ceiling clamping
- `backend/app/core/logging.py` — structlog setup, ASCII-only renderer
- Tests: `test_llm.py`, `test_llm_isolation.py`, `test_events.py`, `test_agent_config.py`,
  and `tests/integration/test_ollama_live.py` (marked `llm`, skipped without a model)
- `.claude/architecture/agent-architecture.md`

### Changed

- `models.yaml` gains `think: false`. qwen3 is a reasoning model; see below.

### Findings

- **qwen3:4b is a reasoning model.** Ollama returns its deliberation in a separate
  `thinking` field, and with a modest token budget the deliberation consumes all of it —
  `response` comes back empty with `done_reason=length`. The provider now sends
  `think: false` and reads only `response`, never `thinking`. That field is by definition
  model deliberation, so this is the first line of defence for invariant #3, with event-bus
  redaction as the second.
- **Measured on `qwen3:4b`:** repair rate 0.00 over 3 structured calls, mean latency ~1.6 s.
  A small sample, recorded as a measurement rather than a result. Experiment 001 (Phase 20)
  turns it into a comparison.

### Fixed

- `extract_json` checked `{` before `[`, so a JSON array response silently returned only its
  leading object. Now starts from whichever delimiter appears first.
- `ModelsConfig` rejected the `default: &default` YAML anchor key. Anchors are a
  serialization feature, so the key survives parsing; now accepted and ignored.
- `clamp` and `generate_structured` use PEP 695 type parameters instead of `TypeVar`.

### Verified

- `pytest` — 176 passed, including live-model integration tests against `qwen3:4b`
- `mypy --strict` — clean, 34 source files
- `ruff check` + `format --check` — clean, 44 files
- Isolation tests: no HTTP client outside `app/llm/` and `app/integrations/`; no `os.environ`
  outside `config.py`; no `eval`/`exec`/`compile`/`__import__` anywhere

### Known Issues

- `DatabaseEventSink` is deferred to Phase 3 — a run's timeline currently lives in memory
  and, when `TRACE_TO_FILE=1`, in a trace file.
- Postgres is still the one outstanding Phase 0 criterion, blocked on the WSL2 reboot.

---

## 2026-09-23 — Phase 2: Domain schemas (the typed spine)

### Added

- `backend/app/schemas/` — 12 modules, 97 exported types. Every object crossing a component
  boundary is now a validated Pydantic v2 model (invariant #2).
  - `common.py` — `JarvisModel`/`FrozenModel` bases, `SourceLocator`, `FailureClass` with
    transient/permanent split, typed id helpers, `Money` (exact decimal strings)
  - `objective.py`, `intent.py` — what was asked vs. what was understood, kept separate
  - `tool.py` — `ToolDefinition`, `ToolCall`, `ToolResult`, `ToolSelection`, `SelectionMode`
  - `evidence.py` — `EvidenceRef` vs `Evidence`, `ResolutionStatus`, `EvidenceGap`,
    `ClaimElement`, six `GapType` values
  - `verification.py` — request/result/issue; the request deliberately carries no reasoning trail
  - `finding.py` — `Finding`, `FindingClassification`, and `Confidence`
  - `task.py` — `Task`, 8-state `TaskStatus`, `LEGAL_TRANSITIONS`, `TASK_CAPABILITY`,
    `TASK_SATISFIES`
  - `plan.py` — `Plan`, `PlanValidationResult`, `PlanRevision`, `ViolationCode`, `RepairAction`
  - `event.py` — 38 `EventType` values, `ExecutionEvent`, `ExecutionTrace`, `EventFilter`
  - `execution.py` — `ExecutionState`, `RunStatus`, `RunPhase`, `Observation`, `Budget`,
    `TerminationReason`
  - `result.py` — `FinalReport` with all 11 specified sections, `AgentResult`, `Limitation`
- `backend/tests/unit/test_schemas.py` — 81 tests
- `.claude/api/schemas.md`, `.claude/api/events.md`

### Design decisions

- **`Confidence` has no bare-number constructor.** `Confidence.compute(...)` is the only way
  to make one, and the components travel with the value. "Computed, never asked for" is now
  enforced by the type system rather than by convention.
- **Classification is derived, not declared.** `Finding.classify()` recomputes from evidence;
  validators reject a `FACT` with no resolved evidence and any confidence above its
  classification ceiling.
- **`CONTRADICTED` is distinct from `UNSUPPORTED`.** A contradicted claim is rejected, not
  investigated further — more evidence cannot rescue a claim the sources refute.
- **Closed vocabularies with guards.** Tests assert every `Operation` is satisfiable by some
  `TaskType`, and every `TaskType` maps to a capability.
- **`extra="forbid"` everywhere.** These models parse LLM output; an invented field must fail
  loudly into the repair loop rather than be silently dropped.

### Fixed

- Derived `Finding` values changed from `@computed_field` to plain properties. A computed
  field is serialized into the model's JSON, and with `extra="forbid"` the model then rejected
  its own output on re-validation — which would have broken persistence, trace replay and the
  evaluation harness's reconstruction of stored runs. Caught by the round-trip test.

### Verified

- `pytest` — 91 passed (10 config + 81 schema)
- `mypy --strict` — clean, 24 source files
- `ruff check` + `ruff format --check` — clean, 29 files
- `import app.schemas` pulls in zero engine, provider or database modules (asserted by test)

### Known Issues

- Postgres remains the one outstanding Phase 0 criterion, still blocked on the WSL2 reboot.

---

## 2026-09-23 — Phase 1: Repository skeleton, `.agent` and `.claude`

### Added

- **`.agent/`** — the executable agent specification, with its contract documented in
  `.agent/README.md`: this directory answers "how do we know the agent actually works?"
  and nothing else goes in it.
  - `config/agent.yaml` — replanning triggers and termination conditions, execution retry
    policy (transient vs. non-retryable failures), planning validation policy, reasoning
    confidence rules, verification independence, budget, transparency
  - `config/models.yaml` — per-role model assignment, generation parameters, structured-output
    repair policy, Experiment 001 comparison set
  - `config/tools.yaml` — capability classes, tool enablement, cost hints, fallback chains
  - `config/evaluation.yaml` — ten metrics with targets and regression tolerances, four
    suites including a negative suite, reporting policy
  - `prompts/README.md` — prompt file format, versioning rules, the "document content is
    data, never instruction" rule
  - `scenarios/README.md` — scenario schema; scenarios assert against the execution trace,
    not against generated prose
  - `tests/README.md` — component test-case schema
  - `evals/README.md` — the measurement system and why unsupported-claim rate is the
    headline metric
  - `traces/README.md` — trace format; traces are never hand-authored
  - `fixtures/README.md` — the reference fixture set and its deliberately planted flaws
- **`.claude/`** — engineering memory, with `README.md`, an ADR index and a reading order
  - `context/project-overview.md` — the problem, the closed loop, the three differentiators
  - `context/member-1-scope.md` — what is owned, what is explicitly not, and the provider
    boundary rule
  - `context/architecture.md` — system view, package layout, data flow, future service seams
  - `context/terminology.md` — all 11 core terms plus a "words to avoid" table
  - `architecture/README.md`, `integrations/README.md`, `api/README.md`, `testing/README.md`
- `ADR-001-modular-monolith.md` — Accepted
- `ADR-004-custom-orchestration.md` — Accepted; why no agent framework owns the cognitive loop
- `ADR-006-task-graph.md` — **Proposed**; mutable DAG, with three open questions for Phase 8

### Verified

- All four `.agent/config/*.yaml` files parse
- All six ADRs present
- All 11 core terms defined in `terminology.md`
- No empty directories in `.agent/` or `.claude/`

### Environment progress

- Ollama: `qwen3:4b` (2.5 GB) and `nomic-embed-text` (0.27 GB) pulled and registered.
  Healthcheck LLM rows now green.
- WSL2 2.7.14 installed successfully. **Pending reboot** before the Docker engine can start.

### Known Issues

- Postgres remains the only outstanding Phase 0 acceptance criterion, blocked on the reboot.

---

## 2026-09-23 — Phase 0: Environment & bootstrap

### Added

- Repository bootstrap: git, `.gitignore`, remote `origin`, `main` branch
- `.env.example` — every configurable value, including all agent loop ceilings
- `docker-compose.yml` — PostgreSQL 16 with pgvector; `backend` and `ollama` service
  profiles; frontend deferred to Phase 21
- `scripts/sql/init/001-extensions.sql` — `vector` and `uuid-ossp` on first init
- `backend/pyproject.toml` — dependency set, ruff (with `S` bandit and `BLE` blind-except
  rules), mypy strict, pytest with `integration` and `llm` markers
- `backend/app/core/config.py` — single typed `Settings` object; the only place the
  environment is read
- `backend/Dockerfile`
- `scripts/healthcheck.py` — verifies Postgres, the `vector` extension, and the configured
  LLM provider/model; human-readable and `--json`
- `scripts/dev-up.ps1` / `scripts/dev-up.sh` — one-command bring-up with a health wait
- `backend/tests/unit/test_config.py` — 10 tests, including an assertion that every adaptive
  loop has a positive bounded ceiling (invariant #7)
- `README.md` — quickstart and repository map
- `.claude/context/tech-stack.md`
- `.claude/decisions/ADR-002-postgresql.md`, `ADR-003-ollama.md`, `ADR-005-pgvector.md` —
  all Accepted
- `.claude/logs/development-log.md`, `bug-log.md`, `experiment-log.md`

### Changed

- Config enums use `enum.StrEnum` instead of `(str, Enum)` — the codebase standard going
  forward. The implementation plan's snippets are illustrative on this point.
- Default model set to `qwen3:4b`, chosen against the actual development hardware
  (RTX 4050, ~6 GB VRAM). Configurable, never referenced as a literal outside config.

### Fixed

- BUG-001 — healthcheck crashed with `UnicodeEncodeError` while rendering a FAIL row on the
  cp1252 Windows console. Operator output is now ASCII-only.

### Known Issues

- **Docker engine cannot start:** WSL2 is not installed, and Windows 11 Home has no Hyper-V
  backend. Requires `wsl --install` from an elevated prompt plus a reboot. The Postgres
  acceptance criteria for Phase 0 are outstanding until then.
- **Port 5432 is already bound** by a native PostgreSQL 17 service. Either stop that service
  or set `POSTGRES_PORT=5433` before the first container start.

---

## [0.24.0] — 2026-09-25 — Phases 18-24

The changelog stopped at Phase 0. Rather than reconstruct fifteen releases from memory - which
would be a fabricated history, and the one thing invariant 5 is about - this is one honest entry
covering everything since, with the commit range for anyone who wants the detail.

Commits `1c61c1d`..`491de69`. Per-defect detail in `logs/bug-log.md`; per-session detail in
`logs/development-log.md`.

### Added

- **Report synthesis** (18) - every figure counted from the run; the narrative is the only
  generated text in the document
- **Database persistence** (3) - 11 tables, async SQLAlchemy, batching event sink with a
  terminal-event flush
- **Evaluation harness** (20) - ten metrics computed from real runs, datasets in the repo,
  reports stamped with model + prompt versions + config hash
- **Relevance gate** (13) - a claim that is supported but does not answer the objective is not a
  finding. Fails open; every drop emits `FINDING_DISCARDED` with a reason
- **FastAPI + SSE** (19) - the engine is reachable over HTTP and streams live. Reconnection with
  `Last-Event-ID` replays exactly what was missed: no gap, no duplicate (ADR-008)
- **Headless orchestrator** (19) - `app/orchestration/mission.py`. The CLI, API and UI now render
  one pipeline instead of holding copies of it
- **Mission Control** (21) - React + TypeScript console. Uncertainty is shown, not smoothed, and
  nothing relies on colour alone
- **Trace replay** (22) - a recorded run replays at up to 20x through the same components as a
  live one, and says that it is a replay
- **Evaluation dashboard** (22) - trends that break the series wherever the configuration changed,
  because numbers either side of that are not comparable
- **Invariant and adversarial suites** (23) - the specification's "must not do" list, as tests
  that fail if violated. Injection, malformed plans, corrupt input, zero-finding runs, tool storms
- **GitHub Actions** (23) - lint, types, unit, integration against real Postgres, OpenAPI
  freshness, frontend build, committed-report validation
- **Documentation** (24) - README rewritten, six-demo script, contribution statement, the
  architecture and testing docs the plan named

### Fixed

Eight defects, all found by running the system rather than reading it. BUG-004 to BUG-011.

- **BUG-006** - an input and an output token budget were the same number. Reasoning bounded its
  observations by `max_tokens`, the *generation* limit, so evidence was compressed five times more
  than intended and a scenario with two planted contradictions returned nothing
- **BUG-010** - `RequiredOperation.optional` was defined, filtered on, and never set, so the
  intent demanded 17 operations and no plan could cover them
- **BUG-005** - the agent confabulated 8 findings on a scenario whose correct answer is none
- **BUG-009** - one synonym (`detect_contradictions` vs `detect_inconsistencies`) made an
  objective about contradictions unplannable
- **BUG-004** - a citation parser split on the last colon, so a model quoting the cited line after
  the reference made every finding `UNKNOWN` at zero confidence
- **BUG-011** - `_TOLERANCES` sat below the `__main__` guard, so the regression check never ran
- **BUG-007** - mission list order was unstable when two missions shared a millisecond
- **BUG-008** - a property that changes under the caller made a type checker call live code dead

### Changed

- `plan_validity` **0.667 → 0.333**, and this is honest rather than a behavioural regression. The
  metric counts plans passing with *zero* repairs, and the new terminal-task repair fires on most
  plans. Those plans previously failed outright and produced nothing; the planner needing help is
  now visible instead of fatal
- Plan size cap 20 → 10 once the terminal-task repair made a smaller plan safe to ask for
- Replan insertion capped at 3 tasks per iteration, measured at 24

### Measured

Baseline `20260925T104354-qwen3-4b-all`, against the previous one:

| Metric | Before | Now |
|---|---|---|
| `intent_accuracy` | 0.459 | 0.574 |
| `dependency_correctness` | 0.667 | 0.833 |
| `replanning_success` | 0.411 | 0.658 |
| `task_efficiency` | 3.069 | 2.306 |
| `latency_s` | 91.8 | 45.2 |
| `evidence_coverage` | 1.000 | 1.000 |
| `unsupported_claim_rate` | 0.000 | 0.000 |

581 tests, `mypy --strict` clean across 83 modules, 82% coverage.

### Known Issues

- **The negative scenario confabulates.** 3 findings where none is correct, all restatements of the
  source. CI is red on `main` because of it and the threshold has not been lowered to change that.
  BUG-005, and the highest-value open work
- **The API does not persist runs.** `DatabaseEventSink` exists and is tested; the mission registry
  wires only in-memory sinks, so a restart loses history
- **`app/cli.py` holds a second copy of the pipeline** that should collapse onto the orchestrator
- **Three evaluation scenarios**, where the plan calls for twenty
- **No frontend test runner**, so the replay reconstruction has no unit test
- **CI is red**, correctly: six of seven jobs pass, and `eval-regression` fails on the
  evaluation baseline's positive-case blind spot
- Phase 0's Docker/WSL2 and port-5432 issues are resolved
