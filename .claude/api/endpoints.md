# HTTP API — v1

Generated schema: [`docs/openapi.json`](../../docs/openapi.json). That file is a **build
input**: the frontend generates its TypeScript types from it. Regenerate with

```bash
python scripts/export_openapi.py          # write it
python scripts/export_openapi.py --check  # fail if it is stale (CI)
```

Run the API with:

```bash
uvicorn app.api.app:create_app --factory --reload
```

## The shape of a session

A mission is **not** a request/response. An investigation takes a minute or more, so
`POST /missions` returns `202` with a run id and the work continues in the background.

```
POST /api/v1/missions            -> 202 {run_id, status: RUNNING, stage: UNDERSTANDING}
GET  /api/v1/missions/{id}/stream -> live events until `event: stream_closed`
GET  /api/v1/missions/{id}/report -> the report, once has_report is true
```

A client that cannot hold a stream open can poll `GET /missions/{id}` instead: `stage` is
kept current while the run proceeds.

## Routes

| Method | Route | Notes |
|---|---|---|
| POST | `/api/v1/missions` | `202`. `429 AT_CAPACITY` when `MAX_CONCURRENT_RUNS` is reached |
| GET | `/api/v1/missions` | Newest first |
| GET | `/api/v1/missions/{id}` | Includes `stage` while still running |
| GET | `/api/v1/missions/{id}/tasks` | Nodes, edges, and the concurrency `waves` |
| GET | `/api/v1/missions/{id}/events` | Paginated (`offset`, `limit`) |
| GET | `/api/v1/missions/{id}/findings` | Findings whole, with evidence and verification |
| GET | `/api/v1/missions/{id}/gaps` | Detected gaps and whether each was closed |
| GET | `/api/v1/missions/{id}/report` | JSON `FinalReport` |
| GET | `/api/v1/missions/{id}/report.md` | The same report as Markdown |
| POST | `/api/v1/missions/{id}/cancel` | `202`; cancellation is cooperative |
| GET | `/api/v1/missions/{id}/stream` | SSE. See [ADR-008](../decisions/ADR-008-sse-over-websocket.md) |
| POST | `/api/v1/documents` | Multipart upload; returns the **parse result**, not an ack |
| GET | `/health` | Reports the model, not just a status |

### Findings are returned whole

Evidence and verification come with the claim rather than from separate endpoints. Splitting
them would let a client render a claim before its verification state arrived, and a claim
shown without its verification state is a claim overstated.

### Uploads return what parsed

`POST /documents` responds with each file's `kind`, `summary` and `truncated` flag. A client
that only learns a file was *accepted* still does not know whether it will contribute
anything — a scanned PDF with no text layer uploads perfectly and yields nothing.

## The error contract

Every 4xx and 5xx has the same body, and always a code:

```json
{
  "error_code": "MISSION_NOT_FINISHED",
  "message": "this mission has no report yet; it is at stage EXECUTING",
  "run_id": "run_a1b2c3d4e5f6",
  "details": { "stage": "EXECUTING" }
}
```

**Render codes, not messages.** A client that branches on message text breaks the moment the
wording improves.

| Code | Status | Meaning |
|---|---|---|
| `INVALID_REQUEST` | 422 | Body did not match the schema; `details.errors` has specifics |
| `MISSION_NOT_FOUND` | 404 | No such run id |
| `MISSION_NOT_FINISHED` | 409 | The resource does not exist **yet** — retry |
| `NO_READABLE_DOCUMENTS` | 422 | Nothing attached could be parsed; no run was started |
| `UNSUPPORTED_DOCUMENT_TYPE` | 422 | The loader cannot parse that extension |
| `DOCUMENT_TOO_LARGE` | 413 | Over the 25 MB ceiling |
| `DOCUMENT_UNREADABLE` | 422 | Stored but unparseable, so it was removed |
| `AT_CAPACITY` | 429 | Too many runs in flight |
| `INTERNAL_ERROR` | 500 | Detail is in the log, deliberately not in the response |

`409` rather than `404` for a report that is still being written is deliberate: the
difference decides whether the client retries or gives up.

## Streaming

Each frame carries an `id` and an `event`:

```
id: evt_4f2a91c0
event: TASK_COMPLETED
data: {"event_id":"evt_4f2a91c0","event_type":"TASK_COMPLETED","t_offset_ms":8431,...}
```

- `event:` is the type, so a client attaches a listener per kind instead of switching on a
  field inside the JSON.
- `t_offset_ms` is relative to `RUN_STARTED`, which is what makes two traces comparable.
- `: keepalive` comment lines every 15s. An agent thinking for 40 seconds must not look like
  an agent that died.
- `event: stream_closed` is terminal. Without it an SSE client reconnects forever against a
  finished run.

**Reconnection.** Send `Last-Event-ID` and you get exactly the events you missed — no gap, no
duplicate. An id this process never issued replays everything rather than nothing, because a
client waiting for events that already happened cannot detect that it is stuck. The
reasoning is in [ADR-008](../decisions/ADR-008-sse-over-websocket.md).

```bash
curl -N http://localhost:8000/api/v1/missions/$RUN/stream
curl -N -H "Last-Event-ID: evt_4f2a91c0" http://localhost:8000/api/v1/missions/$RUN/stream
```

## Cancellation

`202`, not `200`: cancellation is *requested*. The run stops at its next await point — a tool
call or model call boundary — and keeps what it had already established. A cancelled
investigation still reports the findings it reached.

`{"cancelling": false}` means the mission had already finished.
