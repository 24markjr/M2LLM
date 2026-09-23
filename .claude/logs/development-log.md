# Development Log

Chronological record of implementation sessions. Newest entry at the top of its date.
Every session records: what was implemented, what changed, why, which files, which tests,
and what is still broken.

---

## 2026-09-23

### 10:45 IST — Phases 4 & 5: LLM abstraction and the event bus

**Order note.** Built Phase 5 before Phase 4, against the plan's numbering. Phase 4's
telemetry emits `LLM_CALL_COMPLETED` through the bus, so building the bus first avoided an
indirection that existed only to preserve a build order. Recorded rather than quietly done.

**Implemented**

- `app/llm/` — provider protocol, Ollama and Echo providers, structured output with repair,
  prompt library, telemetry, typed errors
- `app/core/events.py` — bus, clock, emitter, three sinks
- `app/core/agent_config.py` — YAML loader with ceiling clamping
- `app/core/logging.py`
- 85 new tests across four unit files plus a live-model integration file

**The finding that mattered: qwen3 is a reasoning model**

The live-model acceptance tests failed on first run. Inspecting the raw Ollama response
explained it:

```
response    = ''
thinking    = 'Hmm, the user just asked me to reply with the single word "ready"...'
done_reason = 'length'
```

Ollama puts a reasoning model's deliberation in a separate `thinking` field, and with
`num_predict=64` the deliberation consumed the entire budget before any answer existed.

Two consequences, and the second is the more interesting one:

1. *Practical.* `think: false` now goes on every request, configurable per role in
   `models.yaml`. Without it every evaluation run pays for deliberation tokens it discards,
   roughly doubling latency.
2. *Architectural.* `thinking` is, definitionally, model deliberation — the exact content
   invariant #3 exists to keep out. The provider reads only `response` and never touches
   the field. This is the first line of defence; event-bus redaction is the second. Added
   `test_reasoning_deliberation_never_enters_the_response` to hold it.

This is the kind of thing ADR-003's "build against the harder case" reasoning predicted:
a local model's quirks surface as real engineering rather than being smoothed over by a
forgiving API.

**Measurement on qwen3:4b**

```
repair_rate=0.00  calls=3  mean_latency_ms=1607
```

With `think: false` and JSON mode, the model produced valid structured output first time on
all three calls. Small sample, and deliberately not asserted as a threshold anywhere — the
test prints it rather than checking it, because asserting a number from n=3 would be
inventing a result. Experiment 001 turns this into a real comparison.

**Design decisions**

- **`generate_structured` never guesses.** After exhausting repairs it raises, carrying the
  raw text and the validation errors. A layer that substituted a default would make every
  downstream finding untrustworthy in a way nothing could detect.
- **The repair prompt carries the validation errors verbatim.** Telling the model
  `count: Input should be greater than or equal to 0` fixes far more than asking it to retry,
  and a test asserts the error text actually reaches the second prompt.
- **`EchoProvider` raises by default when no fixture exists.** Synthesis is opt-in. A
  silently synthesized response would let a test pass while proving nothing about the prompt
  it was meant to exercise.
- **Engines take a `RunEventEmitter`, not a bus plus run id plus clock.** Threading three
  things through ten components is how a transition eventually goes unrecorded.
- **`RunClock` uses `perf_counter`.** A wall-clock adjustment mid-run would produce negative
  offsets and an unorderable trace.
- **A lagging SSE subscriber drops events rather than stalling the run.** The client recovers
  its gap by replaying from `Last-Event-ID`; a stalled investigation does not recover.

**Two bugs found by tests**

1. `extract_json` checked `{` before `[`, so a JSON array response silently returned only
   its leading object — a fragment that would have validated as the wrong thing. Now starts
   from whichever delimiter appears first.
2. `ModelsConfig` rejected the `default: &default` anchor key. YAML anchors are a
   serialization feature, so the key survives parsing into the document. Accepted and
   ignored, with a comment explaining why it is there.

**Files**

```
backend/app/llm/{__init__,provider,ollama,echo,structured,prompts,telemetry,errors}.py
backend/app/core/{events,agent_config,logging}.py
backend/tests/unit/{test_llm,test_llm_isolation,test_events,test_agent_config}.py
backend/tests/integration/test_ollama_live.py
.claude/architecture/agent-architecture.md
.agent/config/models.yaml  (think: false)
```

**Tests**

- `pytest` -> 176 passed, including live calls to `qwen3:4b`
- `mypy --strict` -> clean, 34 source files
- `ruff check` + `format --check` -> clean, 44 files
- Isolation suite now enforces: no HTTP client outside `app/llm/` and `app/integrations/`;
  no `os.environ` outside `config.py`; no `eval`/`exec`/`compile`/`__import__` anywhere;
  `app/schemas` imports nothing from the application; `app/llm` never imports engines

**Known issues**

1. `DatabaseEventSink` deferred to Phase 3. Timelines live in memory and optionally in a
   trace file until then.
2. Postgres still blocked on the WSL2 reboot.
3. No prompt assets exist yet — the library is tested against temporary files. Real prompts
   ship with their engines from Phase 6.

---

### 10:15 IST — Phase 2: Domain schemas (the typed spine)

**Implemented**

- 12 schema modules under `backend/app/schemas/`, 97 exported types
- 81 tests in `backend/tests/unit/test_schemas.py`
- `.claude/api/schemas.md` and `.claude/api/events.md`

**The decision that shaped the phase: making invariants unrepresentable**

The instruction was "confidence is computed, never asked for". The weak version of that is a
convention plus a code review habit. The version built instead: `Confidence` has no
constructor taking a bare value. `Confidence.compute(refs=..., classification=...)` is the
only way to produce one, and the inputs are stored alongside the result.

That turned out to be the right pattern for several rules, so it was applied consistently:

| Rule | How it is now enforced |
|---|---|
| Confidence is computed | No bare-number constructor exists |
| A FACT needs resolved evidence | Model validator rejects it |
| A hypothesis cannot look near-certain | Confidence ceiling per classification, validated |
| Verification must be independent | `VerificationRequest` has no reasoning field; a test asserts the field names never appear |
| A rejection must be explainable | `VerificationResult` requires >= 1 issue for any failing status |
| Degradation is never silent | `degraded=True` requires `degraded_reason` |
| A task cannot complete without running | `LEGAL_TRANSITIONS` + `IllegalTransitionError` |
| Reports cannot present unsupported claims as verified | `FinalReport` validator |

The general principle: prefer making an invalid state unconstructable over documenting that
it should not be constructed.

**Bug found by the round-trip test (worth recording)**

`Finding.resolved_evidence_count` and `has_resolved_evidence` were `@computed_field`. A
computed field is serialized into the model's JSON — and with `extra="forbid"`, the model
then **rejected its own output** on re-validation. That would have broken persistence
(Phase 3), trace replay (Phase 22) and the evaluation harness's reconstruction of stored
runs (Phase 20).

Fixed by making them plain properties. The general rule, now documented in the module:
derived values belong in API response models, not in the wire contract of a stored object.
This is exactly what the round-trip test was written to catch, and it caught it on first run.

**Design notes**

- `EvidenceRef` and `Evidence` are deliberately separate types. A ref is what a claim
  *cites*; evidence is what was actually *found*. An unresolvable citation becomes an
  `UNRESOLVED` ref rather than being dropped, which is what feeds gap detection and the
  hallucination metric.
- `CONTRADICTED` vs `UNSUPPORTED` matters more than it first appears: `actionable` is False
  for the former, so the replanning loop will not burn iterations trying to rescue a claim
  the sources refute.
- `TASK_CAPABILITY` and `TASK_SATISFIES` are the bridges between vocabularies. Two tests
  assert the mappings are total, so planning can never emit work that routing cannot serve.

**Files**

```
backend/app/schemas/{__init__,common,objective,intent,tool,evidence,verification,
                     finding,task,plan,event,execution,result}.py
backend/tests/unit/test_schemas.py
.claude/api/{schemas,events}.md
```

**Tests**

- `pytest` -> 91 passed (10 config + 81 schema)
- `mypy --strict app scripts/healthcheck.py` -> clean, 24 source files
- `ruff check` + `ruff format --check` -> clean, 29 files
- Isolation: `import app.schemas` pulls in no engine, provider or database module

**Known issues**

1. Postgres still blocked on the WSL2 reboot. Phase 3 (persistence) needs it; Phases 4-5
   (LLM abstraction, event bus) do not, so the build order can continue either way.
2. `Money` is defined but unused until the CSV/financial tools land in Phase 9.

---

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
