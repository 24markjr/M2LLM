# Phase 19 — FastAPI + SSE streaming

**Milestone:** M5
**Status:** Complete
**Code:** `backend/app/api/`, `backend/app/orchestration/`
**Contract:** `docs/openapi.json` · **Routes:** `.claude/api/endpoints.md`
**Decision:** [ADR-008](../decisions/ADR-008-sse-over-websocket.md)

> Filed as `phase-09-api.md` because the plan names it that — the API is the ninth
> *component*, built in the nineteenth *phase*.

---

## Why it was built out of order

Phase 21 is the frontend. Its acceptance criterion is *"creating a mission from the UI starts a
real run"*, and its `services/api.ts` is generated from `docs/openapi.json`. Neither existed.

Phase 19 had been deprioritised earlier in favour of the intelligence phases, which was right at
the time — the evaluation harness is a bigger part of the contribution than the UI. But a
frontend with no API is a mock, and a mock is the one thing that falls apart in front of an
evaluator who clicks something. So this was built first and the frontend went on top of it.

---

## The orchestrator came first

Until this phase the only way to run a mission was `app/cli.py`, where the pipeline was
interleaved with `print()`. That made the terminal the one client the engine could have.

`app/orchestration/mission.py` is the same sequence with the printing taken out:

```
objective -> intent -> plan -> execute -> reason -> verify -> gaps -> replan -> report
```

It returns a `MissionResult` and emits events. The CLI, the API and the UI are all renderers of
the same run. Two copies of the sequence would have drifted the moment the API grew its own, and
a fix to one would silently not apply to the other.

Three properties worth naming:

**Stages are announced, not inferred.** `on_stage` is a callback, so a caller showing progress
does not have to watch thirty-nine event types and guess which one means "planning finished".
The CLI prints from it; the registry uses it to keep a mission's phase queryable mid-run.

**Ordinary failures are outcomes, not exceptions.** A plan that will not validate, or an
objective too ambiguous to plan against, are reported in the result with an `error_code`. Nothing
is raised for them.

**Cancellation keeps what the run reached.** `CancelledError` marks the result before
re-raising, so a caller holding it still sees the findings established before the stop. That is
the point of cancelling rather than discarding.

---

## Missions never block a request

`POST /missions` returns **202** with a run id and starts a background task. An investigation
takes a minute or more; a request that waits for one times out.

`MissionRegistry` owns the tasks and, per run, the **event history**. That history is what makes
SSE replay possible: `StreamEventSink` deliberately drops events for a lagging subscriber rather
than stalling the agent — backpressure onto an investigation would be the wrong trade — and the
history is what makes that safe, because the client recovers the gap instead of losing it.

The registry is in-memory and per-process. The database sink (Phase 3) is the durable record;
this exists so a live client can be served without a Postgres round trip per event.

**429, not an invisible queue.** A local model serves one request at a time, so an
accepted-but-queued mission would sit at `PENDING` with no indication of why — identical to one
that had hung. `MAX_CONCURRENT_RUNS` is refused explicitly.

---

## SSE, and the part that is easy to get wrong

The reasoning for SSE over WebSocket is in ADR-008. The contract is **no gap and no duplicate**,
and it rests on three things:

1. **Subscribe before replaying.** `stream.py` joins the live queue *before* reading the history.
   Reversed, an event emitted between those two steps lands in neither and the client is short
   one event with no way to detect it.
2. **Filter the overlap by id.** The deliberate overlap between history and live queue is what
   guarantees no gap; filtering by id is what stops it becoming a duplicate.
3. **An unknown `Last-Event-ID` replays everything.** After a restart the id the client holds was
   issued by a process that no longer exists. Replaying nothing would leave it waiting for events
   that already happened — undetectable, and worse than a duplicate.

Two details that cost debugging time if missed:

- **`event: stream_closed`** is terminal. An SSE client reconnects automatically when a stream
  ends, so a finished run that closes silently produces a reconnect loop forever.
- **`X-Accel-Buffering: no`.** Nginx buffers by default and would hold every event until the run
  ended, defeating the entire purpose.

---

## The error contract

Every 4xx and 5xx has one shape, always with a code — including the failures FastAPI raises
itself, whose default body has no code at all and cannot be branched on.

**409, not 404, for a report that does not exist yet.** The difference between "there is no
report" and "there is no report *yet*" decides whether the client retries or gives up.

Full table in [`.claude/api/endpoints.md`](../api/endpoints.md).

---

## Acceptance

| Criterion | Result |
|---|---|
| `curl -N /stream` shows events live, in order, with `t_offset_ms` | **Pass** — 82 events during a real Aurora run |
| Reconnect with `Last-Event-ID` replays missed events, no duplicates, no gaps | **Pass** — reconnect from event 3 delivered exactly the 79 that followed |
| Cancel returns 202 and the run reaches `CANCELLED` | **Pass** |
| OpenAPI schema generated and committed | **Pass** — `docs/openapi.json`, 12 paths |

Verified against a real uvicorn server as well as the ASGI test transport — the two can differ,
and only one of them is what ships.

`docs/openapi.json` is a **build input**, not documentation:

```bash
python scripts/export_openapi.py            # write it
python scripts/export_openapi.py --check    # fail if stale (CI, Phase 23)
```

---

## Two bugs the tests found

**Mission list order was unstable.** Two missions created in the same millisecond tied on
`created_at`, so list order varied between requests for no reason a user could see. Records now
carry a monotonic sequence. See BUG-007.

**`MissionRecord.finished` was a property**, and mypy narrowed the first truthiness check and
declared every later one dead code. It is mutable state the SSE loop reads repeatedly while the
run proceeds, so it is a method. See BUG-008.

---

## Known gaps

- **The CLI still has its own copy of the pipeline.** The orchestrator exists and the API uses
  it; collapsing `run_investigate` onto it was deliberately deferred to avoid destabilising the
  demo path mid-session. This is duplication that will drift and should be closed.
- **Runs are not persisted from the API.** `DatabaseEventSink` exists (Phase 3) but the registry
  wires only the in-memory sinks, so a restart loses history.
- **Uploads land in `.agent/uploads/` and are never cleaned up.**
- **No authentication.** Deliberate for a local single-user demo; would gate any deployment.
