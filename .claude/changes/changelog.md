# Changelog

All notable changes to JARVIS (Member 1 — intelligence & agent orchestration).
Newest first. Categories: Added · Changed · Fixed · Removed · Known Issues.

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
