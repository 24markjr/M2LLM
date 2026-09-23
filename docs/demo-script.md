# JARVIS — Demo Script

**For:** external evaluator review
**Status at this demo:** Phases 0–2, 4–6 complete. Phase 3 (persistence) blocked on a
pending WSL2 reboot. Phases 7+ not started.

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
call after that is ~3 s. Run any command once before the demo starts.

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

## 2. Live: the agent interprets an objective (2 min)

```bash
cd backend
python -m app.cli intent "Investigate these project reports and determine whether the timeline and budget information is consistent." --docs project_report.pdf financial_report.pdf budget.csv
```

**Point at three things in the output:**

**The pre-pass.** Four operations are derived *before the model is called at all*, from
keywords and file types. The model is never the only signal — and if it fails, the system
still produces a usable intent rather than nothing.

**The execution trace.** Every state transition is recorded with a millisecond offset from
the run start. This is not logging: the whole run is reconstructable from this timeline, and
it's what the UI and the evaluation harness will both read.

```
00:00.000 RUN_STARTED
00:03.256 LLM_CALL_COMPLETED
00:03.257 INTENT_CREATED
00:03.257 RUN_COMPLETED
```

**The structured intent.** Natural language in; a validated object out, with operations drawn
from a closed vocabulary of 18. Note `repair attempts: 0` — that number is measured, not
assumed.

---

## 3. Live: the agent refuses to guess (1 min)

```bash
python -m app.cli intent "Look at these files." --docs report.pdf
```

Output ends with:

```
CLARIFICATION NEEDED
  What specifically should be investigated in these documents - for example a
  consistency check, a comparison, or a summary?
  (an ambiguous objective must not produce a confident plan)
```

> This is the behaviour I care most about at this stage. A system that produces a confident
> plan from a vague request wastes the entire run and produces findings nobody asked for.
> Ambiguity is a valid answer.

---

## 4. The engineering standard (2 min)

```bash
python -m pytest tests -q -m "not llm"     # 196 passed
mypy app                                    # clean, strict mode, 36 files
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

## 5. What's next, honestly (1 min)

| Phase | Status |
|---|---|
| 0-2, 4-6 | Complete: environment, schemas, LLM layer, event bus, intent engine |
| 3 | Blocked on a pending WSL2 install for Docker/Postgres |
| 7-9 | Planner, task graph, tool system - the first end-to-end vertical slice |
| 14, 16 | Evidence gap detection and adaptive replanning - the headline features |
| 20 | Evaluation harness - the measured metrics |

The build order is in `.claude/implementation/implementation-plan.md`, 25 phases with
acceptance criteria per phase.

---

## Questions to expect

**"Isn't this just a wrapper around an LLM?"**
The model proposes free-text operations; the system maps them onto a closed vocabulary and
surfaces anything out-of-vocabulary as explicitly unsupported. That pattern repeats
throughout: the planner will propose a decomposition and the system will validate it into a
legal DAG. The model's output is an input to the system, not the system's output.

**"How do you know it works?"**
196 tests today, plus `.agent/` — scenarios that assert against the *execution trace*, not
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
