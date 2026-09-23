# Development Log

Chronological record of implementation sessions. Newest entry at the top of its date.
Every session records: what was implemented, what changed, why, which files, which tests,
and what is still broken.

---

## 2026-09-23

### 09:30 IST — Phase 1: Repository skeleton, `.agent` and `.claude`

**Implemented**

- Full `.agent/` structure with a README per directory documenting that directory's contract
- Four `.agent/config/*.yaml` behaviour-policy files (agent, models, tools, evaluation)
- Full `.claude/` structure: README + ADR index, four context documents, four section READMEs
- `ADR-001` (modular monolith) and `ADR-004` (custom orchestration) — both Accepted
- `ADR-006` (mutable task DAG) — Proposed, with three open questions for Phase 8

**Design decision recorded this session: two configuration surfaces**

`.env` / `Settings` and `.agent/config/*.yaml` could easily have drifted into duplicating
each other. The split, documented in `.agent/README.md`:

- `.env` -> `Settings`: **where things are, and hard safety ceilings** — database URL,
  provider selection, `MAX_REPLAN_ITERATIONS`, `MAX_PARALLEL_TASKS`. Operator-owned,
  per machine.
- `.agent/config/*.yaml`: **how the agent behaves** — model roles, fallback chains, scoring
  weights, evaluation thresholds. Engineer-owned, committed and reviewed.

**The rule that makes the split safe:** YAML can never exceed an `.env` ceiling. Settings
values are hard caps enforced at load time. If `agent.yaml` requests 8 replan iterations and
`MAX_REPLAN_ITERATIONS=3`, the loader clamps to 3 and logs it. Behaviour policy is tunable
from inside the repo; safety bounds are not. The clamping loader is a Phase 4 deliverable —
until it exists, these YAML files are documented but not yet consumed, and that is stated
in each file's header.

**Also recorded:** `.agent/README.md` now carries a phase-to-file map, so it is explicit
which files are deliberately absent rather than accidentally missing.

**Files**

```
.agent/README.md
.agent/config/{agent,models,tools,evaluation}.yaml
.agent/{prompts,scenarios,tests,evals,traces,fixtures}/README.md
.claude/README.md
.claude/context/{project-overview,member-1-scope,architecture,terminology}.md
.claude/{architecture,integrations,api,testing}/README.md
.claude/decisions/{ADR-001-modular-monolith,ADR-004-custom-orchestration,ADR-006-task-graph}.md
```

**Tests / acceptance**

- All four config YAML files parse -> OK
- Six ADRs present -> OK
- 11/11 core terms defined in `terminology.md` -> OK
- No empty directories under `.agent/` or `.claude/` -> OK
- `pytest` 10 passed, `ruff` clean, `mypy --strict` clean (unchanged — Phase 1 adds no code)

**Environment progress since the last entry**

- Ollama models pulled: `qwen3:4b` (2.5 GB) and `nomic-embed-text` (0.27 GB), both
  registered. The healthcheck's two LLM rows are green.
- WSL2 2.7.14 installed via an elevated `wsl --install`. Both optional features enabled;
  DISM reports changes take effect after reboot.

**Known issues**

1. **Reboot pending.** The Docker engine cannot start until Windows restarts. Postgres is
   the only outstanding Phase 0 acceptance criterion.
2. The first `dev-up` after the reboot will start Postgres on **5433** (set in the local
   `.env`) to avoid the pre-existing native PostgreSQL 17 on 5432.

---

### 00:20 IST — Phase 0: Environment & bootstrap

**Implemented**

- Repository bootstrap: `git init`, remote `origin` -> `github.com/24markjr/M2LLM`, branch `main`
- `.gitignore`, `.env.example` (every variable the system reads, including all loop ceilings)
- `docker-compose.yml` — `postgres` (pgvector/pgvector:pg16) by default; `backend` and
  `ollama` behind profiles. Frontend service deferred to Phase 21 so `docker compose config`
  stays valid.
- `scripts/sql/init/001-extensions.sql` — creates `vector` + `uuid-ossp` on first container init
- `backend/pyproject.toml` — dependencies, ruff, mypy strict, pytest config
- `backend/app/core/config.py` — the single `Settings` object (invariant #7)
- `backend/Dockerfile`
- `scripts/healthcheck.py` — verifies Postgres reachability, the `vector` extension, and the
  configured LLM provider + model. Human-readable and `--json` output.
- `scripts/dev-up.ps1` / `scripts/dev-up.sh` — one-command stack bring-up with health wait
- `backend/tests/unit/test_config.py` — 10 tests, including one that asserts every adaptive
  loop has a positive, bounded ceiling
- `README.md` — quickstart

**Changed**

- Config enums use `enum.StrEnum` rather than `(str, Enum)`. Python 3.12 makes the latter a
  lint error (ruff UP042), and `StrEnum` is the same contract. The implementation plan's
  schema snippets show `(str, Enum)` illustratively; the codebase standard is `StrEnum`.
- Added `BLE` (blind-except) to the ruff rule set, so `except Exception` must be deliberate
  and annotated. The healthcheck legitimately needs broad catches — it reports failures, it
  does not raise them.
- Default model set to `qwen3:4b` after checking the hardware (see Decisions below).

**Decisions taken this session**

- **Database:** WSL2 + Docker + `pgvector/pgvector:pg16`, per ADR-002/ADR-005. Chosen by the
  project owner over two alternatives (native PG17 without pgvector; cloud Postgres).
- **Model:** `qwen3:4b` as the development default on an RTX 4050 laptop (~6 GB VRAM). Fits
  fully in VRAM, keeps the evaluation suite cheap enough to run habitually. Phase 20's
  Experiment 001 will compare it against a larger model on identical scenarios.

**Files**

```
.gitignore  .env.example  docker-compose.yml  README.md
backend/pyproject.toml  backend/Dockerfile
backend/app/__init__.py  backend/app/core/config.py  (+ package __init__ files)
backend/tests/unit/test_config.py
scripts/healthcheck.py  scripts/dev-up.ps1  scripts/dev-up.sh
scripts/sql/init/001-extensions.sql
.claude/context/tech-stack.md
.claude/decisions/ADR-002-postgresql.md  ADR-003-ollama.md  ADR-005-pgvector.md
```

**Tests**

- `pytest tests` -> 10 passed
- `ruff check backend scripts` -> clean
- `mypy --strict app scripts/healthcheck.py` -> clean, 12 source files

**Environment findings**

| Component | Status |
|---|---|
| Python 3.12.10 | OK — venv at `.venv`, `pip install -e "backend[dev]"` succeeded |
| Node 24.19.0 | OK — unused until Phase 21 |
| Docker Desktop 29.8.0 | Installed at `%LOCALAPPDATA%\Programs\DockerDesktop`, **engine cannot start** |
| WSL2 | **Not installed.** This is why the Docker engine fails: Windows 11 Home has no Hyper-V backend, so Docker Desktop requires WSL2. Owner action: `wsl --install` in an elevated prompt, then reboot. |
| PostgreSQL 17 | Running natively as service `postgresql-x64-17` on :5432. Not used — the project targets the pgvector container (ADR-002). Note the port conflict when the container starts. |
| Ollama 0.34.2 | Installed via winget, server responding on :11434 |
| GPU | RTX 4050 Laptop (~6 GB VRAM) + Intel UHD; 15.7 GB system RAM |

**Known issues**

1. **Docker engine down pending WSL2 install.** Blocks the Phase 0 Postgres acceptance
   criteria. Everything else in Phase 0 is complete and verified.
2. **Port 5432 is already bound** by the native PostgreSQL 17 service. When the container
   starts, either stop that service or set `POSTGRES_PORT=5433` in `.env`. Decide at the
   first successful `dev-up` run.
3. Healthcheck rendering crashed on the Windows cp1252 console — fixed, see `bug-log.md`.
