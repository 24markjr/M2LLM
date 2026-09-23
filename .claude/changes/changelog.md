# Changelog

All notable changes to JARVIS (Member 1 — intelligence & agent orchestration).
Newest first. Categories: Added · Changed · Fixed · Removed · Known Issues.

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
