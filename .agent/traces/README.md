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
