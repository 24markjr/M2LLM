# JARVIS — Demo Script

Six demos, ten minutes, and nothing here depends on luck.

Every command below has been run. Every one has a **recorded fallback**, because local inference
on laptop hardware occasionally stalls and a presentation should not be hostage to that. The
fallback is a real recording of a real run, replayed — never a mock, never hand-written
(invariant 5).

---

## Before the room

```bash
ollama serve                                    # leave running
cd backend && python -m app.cli health          # must report provider_healthy
ollama run qwen3:4b "ready"                     # warms the model into memory
```

That last one matters more than it looks. A cold model adds 10–20 seconds to the first call, which
is exactly when everyone is watching.

**Have the web console up as well**, in a second browser tab:

```bash
# terminal 2
cd backend && uvicorn app.api.app:create_app --factory --reload
# terminal 3
cd frontend && npm run dev                      # http://localhost:5173
```

If the model stalls at any point: switch to that tab, go to **`#/replay`**, and play a recording.
It renders through the same components as a live run. Say that it is a replay — the banner says so
anyway, and it is not dismissible.

---

## The one-sentence framing (30 s)

> Most systems built on a language model ask the model how confident it is. This one never does.
> Every claim is bound to the evidence that produced it, confidence is computed from what actually
> resolved, and there is no way in the code to assert a confidence you did not derive.

Then run something.

---

## Demo 1 — Basic investigation

**Shows:** objective → intent → plan → execution → evidence-backed result.

```bash
cd backend
python -m app.cli investigate \
  "Investigate the Aurora project reports and identify any contradictions between the timeline and the financial information." \
  --docs aurora_project_report.txt aurora_financial_report.txt aurora_budget.csv \
  --report aurora.md
```

**What to point at, in order:**

1. **Intent** — the goal and the required operations. The agent decided what kind of work this is;
   nobody configured it.
2. **The task graph** — a DAG, not a list. Roughly 7 tasks.
3. **Findings** — each with a classification, a computed confidence, and the source locators it
   rests on.

**Expected trace:** `RUN_STARTED` → `INTENT_CREATED` → `PLAN_CREATED` → `TASK_GRAPH_CREATED` →
`TOOL_SELECTED` ×n → `TASK_STARTED`/`TASK_COMPLETED` ×n → `OBSERVATION_RECORDED` ×n →
`REASONING_STARTED` → `FINDING_CREATED` ×n → `VERIFICATION_STARTED` → `FINDING_VERIFIED` →
`SYNTHESIS_STARTED` → `RUN_COMPLETED`. Around 95 events, ~45–90 s.

**Fallback:** `#/replay`, newest recording.

---

## Demo 2 — Parallel execution

**Shows:** fan-out, genuine concurrency, convergence.

Same run as Demo 1 — this is the *timing* view of it. Either read the CLI's wave output:

```
execution waves (5):
  wave 0: task_001, task_006   <- these run in parallel
  wave 1: task_002, task_003   <- these run in parallel
  ...
```

or, better, show the **task graph panel** in the web console, which lays the waves out as columns.

**The point:** the waves are computed from the graph, not configured. Two extraction tasks that do
not depend on each other have no edge between them, and that absence is what makes them concurrent.
The parallelism is a property of the plan, not a setting.

**Fallback:** `#/replay` — the graph animates through the waves, which reads better than the CLI
does.

---

## Demo 3 — Evidence gap

**Shows:** gap detected → task created → evidence sought → finding re-verified.

This one is best seen in the console, because the gap renders *on the finding that provoked it*.

1. Run a mission from `#/new` (Aurora objective, all three documents).
2. Wait for findings to appear, then verification.
3. When a finding comes back `UNSUPPORTED`, a **dashed amber block** appears on that card showing:
   - the specific missing element — never "more evidence needed", which would have failed at its job
   - the task the replanning loop **inserted** to go and find it

**What makes this defensible:** the decision that a gap exists is *deterministic*. It comes from
comparing claim elements against resolved evidence, before any model is asked anything. Only the
suggested query is phrased by a model, and only after the gap already exists. A model that could
decide whether a gap exists could also decide there wasn't one.

**If no gap appears:** that is a legitimate outcome — all findings were supported. Use the replay
of a run that did produce one, or move on. Do not re-run hoping for a failure.

**Backing dataset:** [`.agent/evals/datasets/aurora_timeline_only.yaml`](../.agent/evals/datasets/aurora_timeline_only.yaml)
reliably produces gaps (one document, so cross-source claims cannot be supported).

---

## Demo 4 — Failure recovery

**Shows:** tool fails → retry with backoff → fallback tool → run continues.

There is no fixture that makes a real tool fail on demand, so demonstrate this from the **tests**,
which is the honest version:

```bash
cd backend
pytest tests/unit/test_adversarial.py -v -k "tool"
pytest tests/unit/test_execution.py -v -k "retry or fallback"
```

**What to say:** every tool in the registry is replaced with one that always raises. The run still
terminates, marks the graph, and emits `TASK_FAILED` — and a downstream task whose inputs never
arrived is **skipped rather than run on nothing**, because a task that reports success on absent
data is worse than one that fails.

Retries are bounded by `max_task_retries` with exponential backoff; when they are exhausted the
router walks a fallback chain; when that is exhausted the task fails cleanly. Every step is on the
timeline.

**Why not a live failure:** faking one would mean shipping a tool whose job is to break, and that
is a fixture pretending to be a finding. The test is the real demonstration.

---

## Demo 5 — Replanning

**Shows:** the plan changes *while it is running*.

Two ways, depending on what the room wants.

**The evidence:** in the web console task graph, a task the loop inserted is drawn with a **dashed
border**, labelled `INSERTED BY REPLAN`, and it is the only element in the interface that slides in
horizontally. You can point at the moment the plan changed.

**The guarantees**, which matter more than the animation:

```bash
pytest tests/unit/test_replanning.py -v
```

- **It always terminates.** `MAX_REPLAN_ITERATIONS` is a hard ceiling clamped from `.env`.
- **Every stop records a distinct, honest reason.** `ALL_RESOLVED` and `DIMINISHING_RETURNS` are
  both good outcomes and mean different things; `MAX_ITERATIONS` and `NO_ACTIONABLE_GAP` are both
  honest failures and mean different things. A loop that stops silently is indistinguishable from
  one that gave up.
- **A contradicted finding is never retried.** More evidence cannot rescue a claim the sources
  refute; spending iterations on one would be the loop working hard and achieving nothing.
- **One iteration may insert at most 3 tasks.** Measured at 24 before that cap, which drove task
  efficiency to 3.6× the minimum.

---

## Demo 6 — Confidence and verification

**Shows:** finding → evidence → computed confidence → verification → reported status.

Expand any finding card in the console. Or, more convincingly, do this in a Python shell:

```bash
cd backend && python
```

```python
from app.schemas.finding import Confidence
Confidence(value=0.96)
# ValidationError — there is no constructor that takes a bare number
```

**That is the whole argument in one line.** Confidence cannot be asserted anywhere in this system,
only computed, and it is enforced in the type rather than by convention.

Then expand a finding and show the four factors it decomposes into — resolution rate, evidence
strength, source agreement, classification ceiling. A confidence nobody can take apart is
indistinguishable from one that was made up.

**Also show an `UNRESOLVED` citation if one is present.** It was kept, not dropped. A dropped bad
citation leaves a claim that looks fully supported, which is the more dangerous outcome.

---

## The uncomfortable slide — show it before they find it

**Do this deliberately.** It is stronger coming from you.

```bash
cd backend
python -m app.cli investigate \
  "Determine whether the Aurora project report contradicts itself on the approved completion date." \
  --docs aurora_project_report.txt
```

The correct answer is **no findings**. The agent currently produces about three, and they are
restatements of the source — true, correctly cited, and not answers to the question.

**What to say:**

> This is the failure mode the whole system is built to avoid, and I can show you exactly how I
> know about it. It is not a guess — it is measured. The evaluation suite has a negative scenario
> whose correct answer is nothing, it fails the build when the agent finds something, and the
> report names the specific claims it invented. It is BUG-005 in the bug log, it is on the
> evaluation dashboard, and CI is red on `main` because of it. I have not weakened the threshold to
> go green.

Then show `#/evaluation` — the confabulation count sits next to the ten metrics, because no metric
can express it: an agent that invents findings scores 1.000 on coverage, 1.000 on verification and
0.000 on unsupported claims. A perfect score for being exactly wrong.

**Why lead with this:** a reviewer's first question about any agent is "how do you know it isn't
making things up?" The answer is not a reassurance. It is a harness that catches it, a number that
moves, and a build that fails.

---

## Questions to expect

**"Why not LangChain / AutoGPT / CrewAI?"**
[ADR-004](../.claude/decisions/ADR-004-custom-orchestration.md). The contribution *is* the
orchestration — the validated DAG, the evidence binder, the deterministic gap detector, the bounded
replanning loop. Delegating those to a framework would have meant delegating the thing being
evaluated. A framework would also have made invariant 1 unenforceable.

**"How do you know it isn't hallucinating?"**
`unsupported_claim_rate` is 0.000 on the current baseline, `evidence_coverage` is 1.000, and
neither is a reassurance — both are computed from runs over datasets in the repo. And the negative
case above is the honest limit of that claim.

**"Isn't the model just doing all the work?"**
Show `plan_validity` at 0.333 — two plans in three need a deterministic repair before they can
execute. And the intent engine, the validator, the gap detector and the confidence computation
never call a model at all. Then `pytest tests/unit/test_llm_isolation.py` — the source tree is
parsed to prove the model is reachable from exactly one package.

**"Why such a small model?"**
It runs on a laptop, and every number here is honest about it. The abstraction is a `Protocol`, so
swapping model is one environment variable — and a report produced with a different model is
*refused* as incomparable rather than quietly compared.

**"What would you do next?"**
The confabulation is fixed, across two independent negative scenarios. What is left is *recall* -
two positive scenarios find nothing where claims are planted, and the ceiling is the model rather
than the logic. So: a larger model behind the same `Protocol`, and more scenarios. Eight exist
where the plan calls for twenty, and eight is still too few to separate variance from regression.

---

## If the model misbehaves live

In order of preference:

1. **Switch to `#/replay`.** A real recording, at 4x, through the same components. Say it is a
   replay.
2. **Show the committed report** — `.agent/evals/reports/20260925T104354-qwen3-4b-all.md`. The
   numbers exist whether or not the laptop cooperates.
3. **Run the tests.** `pytest tests -m "not llm"` — 581 of them, no model required, in about 18
   seconds. Every invariant is proven there.

Never re-run a failed live demo hoping for a better result. It looks exactly like what it is, and
the recording is better anyway.

---

## What is not built

Worth knowing before someone asks:

- **The API does not persist runs.** The database layer exists and is tested; the registry wires
  only in-memory sinks, so a restart loses history.
- **Three evaluation scenarios, not twenty.**
- **No frontend test runner**, so the replay reconstruction has no unit test.
- **CI is red.** Six of seven jobs pass, including the integration suite against a real
  Postgres. `eval-regression` fails on the evaluation baseline's positive-case blind spot -
  which is that job working, not broken.
