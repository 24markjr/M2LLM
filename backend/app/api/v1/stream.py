"""Server-sent events for a live run. See ADR-008 for why SSE and not WebSocket.

The contract that matters is **reconnect without a gap and without a duplicate**. A client
that drops mid-run reconnects with `Last-Event-ID`, and gets exactly the events it missed:

1. Replay everything in the mission's history after that id.
2. Then attach to the live queue, skipping anything already replayed.

Step 2 is the part that is easy to get wrong. Subscribing happens *before* the replay is
read, not after - otherwise an event emitted between reading the history and subscribing
falls into neither, and the client is silently short one event with no way to detect it.
Events already seen are filtered by id on the way out, which is what keeps the overlap from
becoming a duplicate.

Written without `sse_starlette`: the format is four lines of text and adding a dependency to
produce them would be the larger cost.
"""

from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncIterator

from fastapi import Request
from starlette.responses import StreamingResponse

from app.api.registry import MissionRecord, get_registry
from app.core.logging import get_logger
from app.schemas.event import ExecutionEvent

log = get_logger(__name__)

# How long to wait for an event before sending a comment line. Without this a proxy or a
# load balancer closes an idle connection, and an agent thinking for 40 seconds looks
# exactly like an agent that died.
HEARTBEAT_S = 15.0


def stream_mission(record: MissionRecord, request: Request) -> StreamingResponse:
    last_event_id = request.headers.get("last-event-id")
    return StreamingResponse(
        _events(record, request, last_event_id),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            # Nginx buffers by default, which would hold events until the run ended and
            # defeat the entire point of streaming them.
            "X-Accel-Buffering": "no",
        },
    )


async def _events(
    record: MissionRecord, request: Request, last_event_id: str | None
) -> AsyncIterator[str]:
    stream = get_registry().stream
    # Subscribe first. An event emitted between reading the history and subscribing would
    # otherwise land in neither, and the client would be short one event with no way to know.
    queue = stream.subscribe(record.run_id)
    seen: set[str] = set()

    try:
        for event in record.events_after(last_event_id):
            seen.add(event.event_id)
            yield _format(event)

        if record.is_finished():
            yield _format_done(record)
            return

        while True:
            if await request.is_disconnected():
                return

            try:
                event = await asyncio.wait_for(queue.get(), timeout=HEARTBEAT_S)
            except TimeoutError:
                # A comment line. Keeps the connection open without inventing an event:
                # a synthetic keepalive event would appear in the client's timeline as
                # something the agent did.
                yield ": keepalive\n\n"
                if record.is_finished():
                    yield _format_done(record)
                    return
                continue

            if event.event_id in seen:
                # Replayed already. This is the overlap between history and live queue, and
                # dropping it here is what makes reconnection duplicate-free.
                continue
            seen.add(event.event_id)
            yield _format(event)

            if record.is_finished() and queue.empty():
                yield _format_done(record)
                return
    finally:
        stream.unsubscribe(record.run_id, queue)


def _format(event: ExecutionEvent) -> str:
    """One SSE frame.

    `id:` is what the client echoes back as `Last-Event-ID`, and `event:` is the type, so a
    client can attach a listener per event kind rather than switching on a JSON field.
    """
    payload = {
        "event_id": event.event_id,
        "event_type": event.event_type.value,
        "t_offset_ms": event.t_offset_ms,
        "task_id": event.task_id,
        "finding_id": event.finding_id,
        "payload": dict(event.payload),
    }
    body = json.dumps(payload, default=str)
    return f"id: {event.event_id}\nevent: {event.event_type.value}\ndata: {body}\n\n"


def _format_done(record: MissionRecord) -> str:
    """A terminal frame, so the client closes rather than retrying.

    An SSE client reconnects automatically when the stream ends, so a run that finished
    without saying so produces a reconnect loop against a mission that will never emit again.
    """
    body = json.dumps(
        {
            "run_id": record.run_id,
            "status": record.status.value,
            "stage": record.stage.value,
            "events": len(record.events),
        }
    )
    return f"event: stream_closed\ndata: {body}\n\n"
