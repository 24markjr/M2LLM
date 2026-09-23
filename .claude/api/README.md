# API documentation

The HTTP surface. The engine is reachable over HTTP from Phase 19; these documents are
written alongside it.

| Document | Covers | Phase |
|---|---|---|
| `schemas.md` | The Pydantic domain types — the typed spine | 2 |
| `events.md` | `ExecutionEvent` types, payloads and ordering guarantees | 2, 5 |
| `endpoints.md` | Routes, request/response shapes, error contract, SSE | 19 |

## Vocabulary note

The API says **mission**; the internals say **run**. Same object (`agent_runs`, `run_id`).
The split is deliberate — "run" is precise for engineers, "mission" is meaningful for a user
who is starting an investigation, not invoking a job. See
[`../context/terminology.md`](../context/terminology.md).

## Error contract

Every 4xx/5xx returns a structured body, never a bare string:

```json
{
  "error_code": "PLAN_INVALID",
  "message": "Plan failed validation after 2 repair attempts",
  "run_id": "01JBX...",
  "details": { "violations": ["CYCLE: task_004 -> task_006 -> task_004"] }
}
```

The frontend renders codes, not prose, so error presentation is not hostage to wording.

## Streaming

`GET /api/v1/missions/{id}/stream` is Server-Sent Events, not WebSocket (ADR-008, Phase 19).
Execution updates are one-way, and SSE gives reconnect-and-replay from `Last-Event-ID` for
free — which matters, because a dropped connection mid-run should not lose the timeline.

Events are the same `ExecutionEvent` records that are persisted, carrying `t_offset_ms`
relative to `RUN_STARTED`. Model deliberation is stripped before an event is emitted
(invariant #3), so the stream shows what the agent *did*, not what it was thinking.
