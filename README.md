# JARVIS

**An adaptive, evidence-driven AI orchestration engine.**

JARVIS transforms a high-level natural-language objective into a validated, executable
task graph — selecting tools, executing tasks with dependency awareness, reasoning over
the evidence it collects, detecting what evidence is *missing*, verifying its own
candidate findings, and replanning when the evidence is insufficient.

It is not a chat interface. You give it an objective; it works out how to accomplish it,
and it shows its work.

```
USER OBJECTIVE → INTENT → PLAN → TASK GRAPH → TOOL ROUTING → EXECUTION
      → OBSERVATION → REASONING → FINDINGS → VERIFICATION
             ↓ evidence insufficient
        EVIDENCE GAP → REPLAN → (execute again)
             ↓ evidence sufficient
        SYNTHESIS → EVIDENCE-BACKED REPORT
```

> **Status:** Phase 0 (environment & bootstrap) complete. See
> [.claude/implementation/implementation-plan.md](.claude/implementation/implementation-plan.md)
> for the full phased build order.

---

## Quickstart

**Prerequisites:** Docker Desktop, Python 3.12+, Node 20+ (frontend, from Phase 21),
and [Ollama](https://ollama.com/download) for local inference.

```bash
git clone <repo> && cd jarvis
cp .env.example .env

# 1. Python environment
python -m venv .venv
.venv/Scripts/activate          # Windows;  source .venv/bin/activate elsewhere
pip install -e "backend[dev]"

# 2. Local model
ollama pull qwen3
ollama pull nomic-embed-text

# 3. Infrastructure + verification
./scripts/dev-up.sh             # Windows: .\scripts\dev-up.ps1
```

`dev-up` starts PostgreSQL (with pgvector), waits for it to report healthy, and runs the
environment healthcheck. A green result means every later phase's assumptions hold.

To check the environment on its own:

```bash
python scripts/healthcheck.py           # human-readable
python scripts/healthcheck.py --json    # machine-readable
```

### Running without a local model

Every component reaches the model through a provider abstraction. Setting
`LLM_PROVIDER=echo` swaps in a deterministic fixture provider, which is what CI uses —
the full test suite runs with no network calls and no GPU.

---

## Repository layout

| Path | Contents |
|---|---|
| `backend/` | FastAPI app, agent runtime, intelligence components, tools |
| `frontend/` | React Mission Control UI *(Phase 21)* |
| `.agent/` | Executable agent specification: prompts, scenarios, tests, evals, traces, fixtures |
| `.claude/` | Engineering memory: context, architecture, ADRs, changelog, development log |
| `scripts/` | Environment bring-up and healthcheck |
| `docs/` | Generated API schema, demo script |

`.agent/` answers *"how do we know the agent actually works?"*.
`.claude/` answers *"why is it built this way?"*.

---

## Documentation

- [Implementation plan](.claude/implementation/implementation-plan.md) — the phased build order
- [Tech stack](.claude/context/tech-stack.md) — what we use and why
- [Architecture decisions](.claude/decisions/) — ADRs
- [Changelog](.claude/changes/changelog.md)
