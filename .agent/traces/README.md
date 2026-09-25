# Execution traces

Recorded execution event logs from real runs. Produced by `TraceFileSink` when
`TRACE_TO_FILE=1` (Phase 5).

## Traces are never hand-authored

A hand-written trace is a fabricated result. If a trace in this directory did not come out
of an actual run, it is worse than having no trace at all — it is evidence of behaviour that
never happened. Invariant #5.

Local scratch traces are gitignored (`*.local.json`). Only curated traces are committed.

## Two purposes

**1. Demo insurance.** The UI can replay a stored trace at speed (Phase 22). Local inference
on laptop hardware occasionally stalls, and a presentation should not depend on that. A
replayed trace is visually identical to a live run, and is disclosed as a replay.

**2. Regression baselines.** Diffing a fresh trace against a committed one shows exactly
where behaviour changed — which task got inserted, which verification flipped, which gap
stopped being detected.

## Format

A trace is the ordered event log of one run, plus a header:

```json
{
  "run_id": "01JBX...",
  "objective": "Find inconsistencies between the project timeline and budget.",
  "recorded_at": "2026-09-23T00:20:11Z",
  "model": "qwen3:4b",
  "prompt_versions": { "intent": 1, "planner": 1, "reasoning": 1 },
  "config_hash": "sha256:...",
  "outcome": "COMPLETED",
  "events": [
    { "t_offset_ms": 0,    "type": "RUN_STARTED",           "payload": {} },
    { "t_offset_ms": 420,  "type": "INTENT_CREATED",        "payload": { "goal": "..." } },
    { "t_offset_ms": 1180, "type": "PLAN_CREATED",          "payload": { "task_count": 8 } },
    { "t_offset_ms": 6900, "type": "EVIDENCE_GAP_DETECTED", "payload": { "finding_id": "F2",
                                                                          "missing": "..." } }
  ]
}
```

`t_offset_ms` is relative to `RUN_STARTED`, which is what produces the
`00:00.420 INTENT_CREATED` timeline in the UI and in demo output.

**Payloads carry operational facts only.** Model deliberation is stripped by the redaction
hook before an event is persisted (invariant #3). A trace shows what the agent *did* — task
chosen, tool chosen, evidence retrieved, verification outcome, replan decision — not what it
was thinking.

## Curated traces

| File | Shows | Phase |
|---|---|---|
| `sample_success.json` | A clean run, objective to report | 9 |
| `sample_replan.json` | Gap detected, plan revised, finding resolved | 16 |
| `sample_failure.json` | Tool failure, retry, fallback, honest degradation | 11 |

---

## Committed recordings

One, currently.

### `aurora-contradiction-demo.json`

A real run of the reference objective — the Aurora contradiction case over all three fixture
documents. Recorded 2026-09-25 on `qwen3:4b`.

| | |
|---|---|
| Events | 95 |
| Duration | 125 s |
| Tasks | 7, in 5 waves |
| Findings | 4, of which 3 verified |
| Outcome | `COMPLETED` |
| Report | present |

**What it demonstrates:** the full pipeline end to end — intent, a validated DAG, concurrent
execution by wave, findings bound to source locators with computed confidence, verification
verdicts, and the synthesised report. It backs demos 1, 2, 3 and 6 in
[`docs/demo-script.md`](../../docs/demo-script.md).

**What it does not demonstrate:** this run inserted **no** tasks by replanning
(`inserted_by_replan: 0`), so it cannot stand in for demo 5's "point at the moment the plan
changed". Demo 5 leans on `tests/unit/test_replanning.py` instead, which proves the properties that
actually matter — the loop terminates, every stop records a distinct reason, and a contradicted
finding is never retried.

Demo 4 (failure recovery) has no recording either, deliberately: making a tool fail on demand would
mean shipping a tool whose job is to break. The adversarial suite is the demonstration.

So **"every demo has a recorded fallback" is not fully met** — four of six do. The other two have a
test suite as their fallback, which for those two is the more honest evidence anyway.

## Adding one

Every mission started through the API records itself here as `<run_id>.local.json`, which is
gitignored. To keep one, rename it without the `.local` — that rename is what makes committing a
recording a considered act rather than an accident of whatever ran last.

Before committing one, check it actually shows what you intend: a run that happened not to detect a
gap or insert a task will replay faithfully and demonstrate nothing.
