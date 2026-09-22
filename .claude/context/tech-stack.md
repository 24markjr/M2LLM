# Tech Stack

**Last updated:** 2026-09-23 (Phase 0)

Every choice here is justified by what the agent runtime needs, not by familiarity.
Where a choice was contested, it has an ADR.

---

## Backend

| Component | Choice | Why |
|---|---|---|
| Language | Python 3.12 | `StrEnum`, native generics, `asyncio.TaskGroup` — the execution engine (Phase 11) leans on structured concurrency |
| Web framework | FastAPI | Native async, Pydantic-based validation, generated OpenAPI, first-class SSE via `StreamingResponse` |
| Validation | Pydantic v2 | Invariant #2: everything crossing a component boundary is a validated model. Also the schema source for structured LLM output (Phase 4) |
| Config | pydantic-settings | One `Settings` object; nothing reads `os.environ` directly (invariant #7) |
| ORM | SQLAlchemy 2.0 (async) | Typed `Mapped[...]` declarative models; async engine matches the runtime |
| DB driver | asyncpg | Fastest async PostgreSQL driver; the event sink writes on the hot path |
| Migrations | Alembic | Reproducible schema; `upgrade head` on a clean DB is a Phase 3 acceptance criterion |
| Vectors | pgvector | Embeddings live in the same database as structured state — see ADR-005 |
| HTTP client | httpx | Async, used only inside `app/llm/` and `app/integrations/` (invariant #1) |
| Logging | structlog | Structured events, not string soup; pairs with the execution event log |
| PDF | pypdf | Document extraction tool (Phase 9) needs page numbers to build evidence locators |

## Inference

| Component | Choice | Why |
|---|---|---|
| Local runtime | Ollama | Runs entirely offline, no API keys, no per-token cost during heavy evaluation runs — see ADR-003 |
| Default model | configurable (`OLLAMA_MODEL`) | Never hard-coded. Experiment 001 (Phase 20) compares models on the same scenarios |
| Embeddings | `nomic-embed-text` (768-dim) | Matches the `vector(768)` column; configurable via `EMBEDDING_DIM` |
| Abstraction | `LLMProvider` protocol | `OllamaProvider` and `EchoProvider` today; a hosted API provider drops in without touching any engine |

## Data

| Component | Choice | Why |
|---|---|---|
| Database | PostgreSQL 16 | Relational integrity for the run/task/finding/evidence graph, `JSONB` for payloads, `vector` for embeddings — see ADR-002 |
| Image | `pgvector/pgvector:pg16` | Postgres + the extension pre-built, so `CREATE EXTENSION vector` just works |

## Frontend *(Phase 21)*

| Component | Choice | Why |
|---|---|---|
| Framework | React + TypeScript + Vite | Fast HMR; typed against the generated OpenAPI schema |
| Styling | Tailwind CSS | Consistent design tokens without a component-library opinion |
| Server state | React Query | Cache + refetch for mission/task/finding reads |
| Client state | Zustand | The SSE stream is event-sourced into a single store |
| Charts | Recharts | Evaluation dashboard — metric trends across eval reports |
| Animation | Framer Motion | Task-graph state transitions; replan insertions must be *visibly* obvious |

## Tooling

| Component | Choice | Why |
|---|---|---|
| Lint | ruff | Includes `S` (bandit) — enforces "no `eval`/`exec`" from the spec's must-not-do list, and `BLE` so every blind `except` is deliberate |
| Types | mypy `--strict` | The typed spine (Phase 2) is only real if it is checked |
| Tests | pytest + pytest-asyncio | `asyncio_mode = auto`; markers `integration` and `llm` gate environment-dependent tests |
| Test ordering | pytest-randomly | Catches order-dependent tests, which agent state is prone to |
| Containers | Docker Compose | Postgres only by default; backend/frontend run natively for fast reload |

---

## Architecture shape

Modular monolith (ADR-001). One deployable backend, hard internal boundaries:

```
FastAPI
  └── Agent Runtime
        ├── Intent Engine        app/intelligence/intent/
        ├── Planner              app/intelligence/planner/
        ├── Task Graph           app/intelligence/graph/
        ├── Tool Router          app/intelligence/router/
        ├── Execution Engine     app/intelligence/execution/
        ├── Context Manager      app/intelligence/context/
        ├── Reasoning Engine     app/intelligence/reasoning/
        ├── Evidence Gap         app/intelligence/evidence_gap/
        ├── Replanning           app/intelligence/replanning/
        └── Synthesis            app/intelligence/synthesis/
              ↓
          LLMProvider  (app/llm/)  ← the only door to the model
              ↓
          PostgreSQL + pgvector
```

---

## Versions pinned at Phase 0

Installed and verified 2026-09-23 on Windows 11, Python 3.12.10:

```
fastapi 0.141.1      pydantic 2.13.5        sqlalchemy 2.0.54
uvicorn 0.53.0       pydantic-settings      asyncpg 0.31.0
alembic 1.20.0       2.15.0                 pgvector 0.5.0
httpx 0.28.1         structlog 26.1.0       pypdf 6.19.0
ruff 0.16.8          mypy 2.3.1             pytest 9.1.1
```

Lower bounds live in `backend/pyproject.toml`. A lock file is introduced at Phase 23
when CI needs byte-reproducible installs.

## Runtime environment verified at Phase 0

| Component | Version | Notes |
|---|---|---|
| Python | 3.12.10 | venv at `.venv/` |
| Node | 24.19.0 | unused until Phase 21 |
| Ollama | 0.34.2 | user-scope install, serving on :11434 |
| Default model | `qwen3:4b` | ~2.6 GB, fits fully in 6 GB VRAM — see ADR-003 |
| Embedding model | `nomic-embed-text` | 768-dim, matches the `vector(768)` column |
| GPU | RTX 4050 Laptop (~6 GB) | Intel UHD as secondary |
| Docker Desktop | 29.8.0 | **requires WSL2** on Windows 11 Home — see the development log |
| PostgreSQL (native) | 17 | pre-existing service on :5432; the project targets the container instead, so watch for the port conflict |
