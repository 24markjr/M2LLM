# Execution Events — the run timeline

**Phase:** 2 (types) / 5 (bus and sinks) · **Location:** `backend/app/schemas/event.py`

---

## The guarantee

> A run must be fully reconstructable from its event log alone.

That is invariant #4, and it is a strong claim deliberately: it forces every state
transition through `emit()`, which in turn means the UI, the demo replay and the evaluation
harness all read the same record rather than three different approximations of it.

It is also what makes a trace a genuine artifact. A log is something you read when
debugging; this is the run.

---

## Event shape

```python
ExecutionEvent(
    event_id="evt_a1b2c3d4e5f6",
    run_id="run_0123456789ab",
    event_type=EventType.EVIDENCE_GAP_DETECTED,
    t_offset_ms=6900,
    payload={"finding_id": "F-002", "missing": "approved baseline completion date"},
    task_id=None,
    finding_id="F-002",
    revision=0,
)
```

Events are **frozen**. The log is append-only — a history that can be rewritten is not a
record.

### `t_offset_ms`, not wall-clock

Every event carries milliseconds since `RUN_STARTED`. This is what produces the timeline
format used in demos and in the UI's trace panel:

```
00:00.000 RUN_STARTED
00:00.420 INTENT_CREATED
00:01.180 PLAN_CREATED
00:06.900 EVIDENCE_GAP_DETECTED F-002
00:07.000 REPLAN_STARTED
00:07.050 TASK_CREATED task_009
00:09.520 RUN_COMPLETED
```

Relative offsets make traces comparable across runs and machines. Absolute timestamps would
make every trace look different for no useful reason. `offset_display` renders the format;
`describe()` renders a full line, ASCII-only (see BUG-001).

---

## Redaction — where invariant #3 is enforced

Events carry **operational** facts: what was selected, what ran, what was found, what was
verified, why the plan changed. Never the model's deliberation.

```python
REDACTED_PAYLOAD_KEYS = {
    "raw_response", "raw_completion", "prompt", "system_prompt",
    "messages", "chain_of_thought", "reasoning_trace", "thinking",
}
```

`event.redacted()` strips these, and the event sink applies it before anything reaches the
database, the SSE stream or a trace file. A component may put raw model output in a payload
while debugging locally; it will not survive to storage.

This gives explainability without exposing private reasoning — the distinction the
specification is explicit about.

---

## The vocabulary

38 types, closed at Phase 2. Closed because the UI renders per type, scenarios assert on
ordered sequences of them, and the evaluation harness counts them — a type invented ad hoc
at a call site would be invisible to all three.

| Group | Types |
|---|---|
| Run lifecycle | `RUN_STARTED`, `RUN_COMPLETED`, `RUN_FAILED`, `RUN_CANCELLED` |
| Understanding | `INTENT_CREATED`, `PLAN_CREATED`, `PLAN_REVISED`, `TASK_GRAPH_CREATED` |
| Tasks | `TASK_CREATED`, `TASK_READY`, `TASK_STARTED`, `TASK_COMPLETED`, `TASK_FAILED`, `TASK_RETRYING`, `TASK_BLOCKED`, `TASK_SKIPPED` |
| Tools | `TOOL_SELECTED`, `TOOL_EXECUTED`, `TOOL_FAILED`, `OBSERVATION_RECORDED` |
| Reasoning | `REASONING_STARTED`, `FINDING_CREATED`, `REASONING_REVISED` |
| Verification | `VERIFICATION_STARTED`, `FINDING_VERIFIED`, `FINDING_REJECTED`, `VERIFICATION_DEGRADED`, `VERIFICATION_COMPLETED` |
| Adaptive loop | `EVIDENCE_GAP_DETECTED`, `EVIDENCE_GAP_RESOLVED`, `REPLAN_STARTED`, `REPLAN_COMPLETED` |
| Output | `SYNTHESIS_STARTED`, `SYNTHESIS_COMPLETED` |
| Instrumentation | `LLM_CALL_COMPLETED`, `BUDGET_WARNING` |

`PHASE_EVENTS` marks the subset that advances the UI's phase tracker.

Two events exist specifically so that degradation is never invisible:
`VERIFICATION_DEGRADED` (the remote verifier was unavailable and baseline was used) and
`BUDGET_WARNING`. A run that quietly did less than it appeared to should say so.

---

## `ExecutionTrace` — the file format

What `TraceFileSink` writes to `.agent/traces/` when `TRACE_TO_FILE=1`:

```json
{
  "run_id": "run_0123456789ab",
  "objective": "Find inconsistencies between the timeline and budget.",
  "recorded_at": "2026-09-23T09:41:02Z",
  "model": "qwen3:4b",
  "prompt_versions": { "intent": 1, "planner": 1, "reasoning": 1 },
  "config_hash": "sha256:...",
  "outcome": "COMPLETED_WITH_GAPS",
  "events": [ ... ]
}
```

The stamps are what make two traces comparable. A trace without its model and prompt
versions cannot be used as a regression baseline, because a difference could be a code
change or just a different model.

**Traces are never hand-authored.** A hand-written trace is evidence of behaviour that never
happened.

### `contains_ordered()` — the core scenario assertion

```python
trace.contains_ordered([
    EventType.EVIDENCE_GAP_DETECTED,
    EventType.REPLAN_STARTED,
    EventType.TASK_CREATED,
])
```

This is how a scenario proves the agent *did the work* rather than guessed a plausible
answer. Asserting on the final report would not catch an agent that skipped the middle;
asserting that a gap was detected **before** replanning started, which was **before** a task
was created, does.

Order matters and is checked: replanning cannot precede the gap that caused it.

---

## `EventFilter` — reads and SSE replay

```python
EventFilter(run_id=..., after_offset_ms=6900, types={EventType.TASK_COMPLETED})
```

`after_offset_ms` is what makes SSE reconnection work (Phase 19). A client that drops
mid-run reconnects with `Last-Event-ID` and replays exactly what it missed — no duplicates,
no gaps.

---

## Sinks (Phase 5)

| Sink | Destination | Notes |
|---|---|---|
| `DatabaseEventSink` | `execution_events` | Append-only; redaction applied first |
| `StreamEventSink` | SSE subscribers | Live UI updates |
| `TraceFileSink` | `.agent/traces/*.json` | Only when `TRACE_TO_FILE=1` |

Sink failures are isolated: a failing sink must never kill a run. Losing a trace file is an
inconvenience; losing the investigation is not acceptable.
