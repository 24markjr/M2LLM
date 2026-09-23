# JARVIS — Demo Script

**For:** external evaluator review
**Status at this demo:** Phases 0-2, 4-7 complete. Phase 3 (persistence) blocked on a
pending WSL2 reboot. Phases 8+ not started.

Be straight about what this is: **the foundation and the first agent component**, built to a
standard, not a finished product. What follows is what actually runs today.

---

## Before the room

```bash
cd D:\M2LLM
.venv\Scripts\activate
python -m app.cli health          # run from backend/
```

**Warm the model first.** The first call loads qwen3:4b into VRAM and takes ~36 s; every
call after that is ~3 s for intent, ~60 s for a full investigate (two calls, the planner
emits a lot of tokens). Run any command once before the demo starts.

```bash
cd backend
python -m app.cli intent "warm up" 
```

---

## 1. The problem, in one sentence (30 s)

> Most AI assistants are `prompt -> LLM -> answer`. That works for questions. It does not
> work for *tasks*, because the right sequence of steps depends on what the earlier steps
> find. JARVIS turns an ambiguous objective into a controlled, evidence-aware process.

---

## 2. Live: objective to a validated task graph (3 min)

**This is the main demo.** One command, end to end.

```bash
cd backend
python -m app.cli investigate "Investigate these project reports and determine whether the timeline and budget information is consistent." --docs project_report.pdf financial_report.pdf budget.csv
```

Takes ~60 s warm (two model calls). Talk while it runs.

**Point at four things in the output:**

**The trace.** Every state transition with a millisecond offset. The run is reconstructable
from this alone - it is what the UI and the evaluation harness will both read.

**The task graph.** 13 tasks with real dependencies. Nobody wrote these steps; the agent
decomposed the objective itself.

**The execution waves.** This is the bit worth pausing on:

```
  wave 1: task_002, task_003   <- these run in parallel
  wave 2: task_004, task_005   <- these run in parallel
```

> Extracting the timeline from one document and the budget from another are independent, so
> the graph says so and they can run concurrently. Comparing them depends on both. That is a
> DAG doing work, not a list of steps.

**The validation line.**

```
validation      : PASSED
clean           : True  (no repairs, no re-prompts)
```

> `clean` is the important word. The model proposed this decomposition; the *system* checked
> it for cycles, dangling dependencies, orphan tasks and whether it actually covers every
> operation the intent required. `clean` means it passed first time with no repairs. A plan
> that needed three repairs is valid but rescued, and we count those separately - otherwise
> a planner could silently degrade and the metric would never notice.

---

## 3. Live: the agent refuses to guess (1 min)

```bash
python -m app.cli investigate "Look at these files." --docs report.pdf
```

Stops before planning:

```
CLARIFICATION NEEDED
  What specifically should be investigated in these documents - for example a
  consistency check, a comparison, or a summary?
  (planning stops here - an ambiguous objective must not produce a plan)
```

> A system that plans confidently from a vague request wastes the whole run and produces
> findings nobody asked for. Ambiguity is a valid answer.

---

## 4. If asked: what stops a bad plan executing (1 min)

Show `app/intelligence/planner/validator.py`. Ten violation codes, each with a test that
feeds the validator a deliberately malformed plan:

| Violation | Why it matters |
|---|---|
| `CYCLE` | Would hang the scheduler. The path is reported, not just the fact |
| `UNCOVERED_OPERATION` | The plan silently dropped part of the request |
| `ORPHAN_TASK` | Output produced and discarded - wasted budget |
| `NO_TERMINAL_TASK` | Nothing consumes the analysis, so no report |

If the model cannot produce a legal plan in three attempts, the run fails with
`PLAN_INVALID` rather than executing something malformed.

---

## 5. The engineering standard (2 min)

```bash
python -m pytest tests -q -m "not llm"     # 223 passed
mypy app                                    # clean, strict mode, 39 files
```

**Show `tests/unit/test_llm_isolation.py`.** It's the most unusual thing in the repo. It
fails the build if any module outside `app/llm/` imports an HTTP client, if anything outside
`config.py` reads `os.environ`, or if `eval`/`exec` appears anywhere. The architectural
claim "the LLM is a component, not the architecture" is *checked*, not asserted in a README.

**Show `Confidence` in `app/schemas/finding.py`** if there's time:

```python
Confidence(value=0.96)          # ValidationError - no such constructor
Confidence.compute(refs=..., classification=...)   # the only way
```

> Confidence is computed from resolved evidence. A model's self-reported certainty has
> nowhere to put itself. That's enforced by the type system rather than by a convention
> someone has to remember.

---

## 6. What's next, honestly (1 min)

| Phase | Status |
|---|---|
| 0-2, 4-7 | Complete: environment, schemas, LLM layer, event bus, intent engine, planner |
| 3 | Blocked on a pending WSL2 install for Docker/Postgres |
| 8-9 | Task graph engine and tool system - the first executing vertical slice |
| 14, 16 | Evidence gap detection and adaptive replanning - the headline features |
| 20 | Evaluation harness - the measured metrics |

The build order is in `.claude/implementation/implementation-plan.md`, 25 phases with
acceptance criteria per phase.

---

## Questions to expect

**"Isn't this just a wrapper around an LLM?"**
The model proposes free-text operations; the system maps them onto a closed vocabulary and
surfaces anything out-of-vocabulary as explicitly unsupported. That pattern repeats
throughout: the planner proposes a decomposition and the system validates it into a
legal DAG. The model's output is an input to the system, not the system's output.

**"How do you know it works?"**
223 tests today, plus `.agent/` — scenarios that assert against the *execution trace*, not
the prose. An agent can produce a plausible report while skipping every step that made it
trustworthy; asserting on the trace catches that, asserting on the output does not. The
evaluation harness in Phase 20 computes ten metrics, none hard-coded.

**"Why a local model?"**
Evaluation is the dominant cost driver — the whole suite runs across 20+ scenarios
repeatedly. Metered API calls would make measuring something you think twice about. It also
forced the structured-output repair loop to be a real component. ADR-003 has the reasoning.

**"What was hard?"**
Two things worth mentioning. qwen3 is a reasoning model — Ollama returns its deliberation in
a separate field, and it consumed the whole token budget, so every structured call returned
empty. Fixing it also mattered architecturally: that deliberation is exactly what the
no-hidden-reasoning rule keeps out of the record. And a JSON extraction bug that returned the
first element of an array instead of the array — still valid JSON, so nothing would have
raised; a reasoning engine asked for candidate findings would have silently received one.
Both are in `.claude/logs/bug-log.md`.

---

## If the model misbehaves live

Set `LLM_PROVIDER=echo` in `.env` and rerun — the deterministic provider serves fixtures with
no network. Say so if you use it; a replay presented as a live run would be exactly the kind
of thing this project is built to prevent.
