# Integration tests

**Location:** `backend/tests/integration/` · **Strategy:**
[testing-strategy.md](testing-strategy.md)

```bash
docker compose up -d postgres
cd backend && alembic upgrade head
pytest tests/integration -p no:randomly -v      # real Postgres, EchoProvider
pytest -m llm                                   # real Ollama; excluded from CI
```

## Two suites, two different dependencies

| File | Needs | In CI |
|---|---|---|
| `test_persistence.py` | Postgres + pgvector | **yes** |
| `test_ollama_live.py` | Ollama with `qwen3:4b` pulled | no |

`test_persistence.py` uses `EchoProvider`. The database is the thing under test; adding model
non-determinism on top would make a failure impossible to attribute.

`test_ollama_live.py` is marked `llm` and deselected by `-m "not llm"`. It is the only place the
real provider is exercised, and it is where the `app/llm/ollama.py` HTTP paths get their coverage.

## They skip themselves locally and must not in CI

Both suites skip with a clear reason when their dependency is missing — `no database reachable
(docker compose up -d postgres)`. That is right locally: a developer without Docker running should
still get a useful suite.

It is wrong in CI, where a skip is a **green tick over nothing**. The workflow therefore runs the
integration suite and then greps for the skip message, failing explicitly if it appears.

## Three test-infrastructure bugs worth knowing about

All three were in the tests, not the code, and all three presented as `RuntimeError: Event loop is
closed` from deep inside asyncpg — which points nowhere useful.

1. **The engine was cached across event loops.** pytest-asyncio gives each test its own loop; a
   pooled connection created under one cannot be reused or even closed under the next. Fixed by
   `dispose_engine()` in an autouse fixture after every test. Slower than sharing a pool, and
   correct — the right trade for a suite that exists to catch real persistence bugs.
2. **A collection-time probe leaked a dead engine.** The "is a database reachable" check created
   an engine during collection, under a loop that was gone by the time any test ran.
3. **Windows' Proactor loop breaks asyncpg teardown.** Fixed with
   `WindowsSelectorEventLoopPolicy` in `conftest.py`, scoped to `sys.platform == "win32"` and to
   tests only — production runs one loop for the process lifetime and never hits it.

`-p no:randomly` is set for this suite because schema setup is ordered. It is the only opt-out
from random ordering in the project.

## What is covered

Eleven tables with their cascades, the batching `DatabaseEventSink` including its terminal-event
flush, repository round-trips, and that a run is reconstructable from its persisted events
(invariant 4).

## Known gap

**The API does not persist runs.** `DatabaseEventSink` is tested here and works, but
`MissionRegistry` wires only the in-memory sinks — so a restart loses history, and no integration
test covers the API-to-database path because that path does not exist yet.
