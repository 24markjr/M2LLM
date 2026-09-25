# ADR-008 — Server-sent events, not WebSocket, for live execution

## Status

Accepted — 2026-09-24 (Phase 19)

## Context

A mission takes a minute or more. The client needs to see it happen — tasks starting, findings
appearing, the plan being revised mid-run — rather than waiting for a single response. That
requires a push channel.

The traffic is entirely one-way. The frontend sends exactly two things during a run, and both
are ordinary requests: creating the mission and cancelling it. Everything else flows from
server to client.

## Decision

Stream execution events over **server-sent events** at
`GET /api/v1/missions/{id}/stream`, and keep every client-to-server action an ordinary HTTP
request.

## Why not WebSocket

WebSocket is the reflexive choice and it is the wrong one here.

**It is bidirectional, and we have no upstream traffic.** A duplex channel for a simplex
problem means writing a message router, a message type vocabulary and a schema for messages
that are never sent.

**Reconnection would be ours to build.** This is the decisive point. A dropped connection
mid-run is the normal case, not the edge case — a laptop sleeps, a proxy times out, a
tunnel restarts. SSE has reconnection in the protocol: the browser reconnects on its own and
sends `Last-Event-ID`, the id of the last event it received. With WebSocket we would design a
resume handshake, a sequence numbering scheme and a replay negotiation, and get them subtly
wrong at least once.

**It complicates the deployment.** SSE is an HTTP response with a media type. It passes
through proxies, CDNs and corporate networks that need explicit configuration to carry a
WebSocket upgrade.

## What the choice obliges us to get right

SSE gives reconnection *hooks*; the guarantee still has to be implemented. The contract is
**no gap and no duplicate**, and it rests on three things:

1. **Per-run event history.** `StreamEventSink` deliberately drops events for a lagging
   subscriber rather than stalling the agent — backpressure onto an investigation would be
   the wrong trade. The history in `MissionRegistry` is what makes that safe: a client
   recovers the gap rather than losing it.

2. **Subscribe before replaying.** `app/api/v1/stream.py` joins the live queue *before*
   reading the history. Reversed, an event emitted between reading the history and
   subscribing lands in neither, and the client is silently short one event with no way to
   detect it. Events already replayed are then filtered by id, which is what keeps the
   deliberate overlap from becoming a duplicate.

3. **An unknown `Last-Event-ID` replays everything.** After a restart, the id a client holds
   was issued by a process that no longer exists. Replaying nothing would leave it waiting
   for events that already happened — worse than a duplicate, because it is undetectable.

Two further details that are easy to miss and expensive to debug:

- **A terminal frame.** An SSE client reconnects automatically when a stream ends, so a
  finished run that closes without saying so produces a reconnect loop against a mission that
  will never emit again. `event: stream_closed` tells the client to stop.
- **`X-Accel-Buffering: no`.** Nginx buffers responses by default, which would hold every
  event until the run ended and defeat the entire purpose.

## Consequences

- Reconnection is tested, not assumed — see `tests/unit/test_api.py`, which asserts that a
  client reconnecting with `Last-Event-ID` receives exactly the events it missed.
- Browsers cap HTTP/1.1 connections per origin at six, so six concurrent streams per origin
  is the practical ceiling. Under HTTP/2 this disappears. It is irrelevant at the scale this
  system runs at, and noted so it is not discovered later as a mystery.
- SSE carries text only. Every event payload is already JSON, so this costs nothing.
- If the UI ever needs genuine bidirectional traffic — steering a run while it executes,
  rather than cancelling it — this decision should be revisited rather than worked around.

## Alternatives considered

**Polling `GET /events?offset=`.** Simplest, and it already exists for pagination and for
reconstructing a finished run. Rejected as the live channel: a poll interval short enough to
feel live wastes requests, and one long enough to be cheap makes the agent look frozen while
it thinks.

**Long-polling.** Reconnection semantics roughly as good, without a standard the browser
implements for us. No advantage over SSE.
