"""The event bus — the single path every state transition takes.

Invariant #4 says a run must be fully reconstructable from its event log alone. That only
holds if there is exactly one way to record a transition, so every engine emits here and
nothing writes the timeline directly.

Three properties this module is responsible for:

**Redaction.** Model deliberation is stripped before an event reaches any sink (invariant
#3). A component may put raw completion text in a payload while debugging; it will not
survive to the database, the SSE stream or a trace file.

**Relative time.** Every event carries `t_offset_ms` from `RUN_STARTED`, which is what makes
traces comparable across runs and machines, and what produces the `00:00.420 INTENT_CREATED`
timeline.

**Sink isolation.** A failing sink must never kill a run. Losing a trace file is an
inconvenience; losing the investigation is not.
"""

from __future__ import annotations

import asyncio
import json
import time
from pathlib import Path
from typing import Protocol, runtime_checkable

from app.core.config import get_settings
from app.core.logging import get_logger
from app.schemas.common import JsonDict
from app.schemas.event import EventType, ExecutionEvent, ExecutionTrace

log = get_logger(__name__)


class RunClock:
    """Monotonic offsets from the moment a run started.

    Uses `perf_counter`, not wall-clock: a system clock adjustment mid-run would otherwise
    produce negative offsets and a trace that cannot be ordered.
    """

    def __init__(self) -> None:
        self._start = time.perf_counter()

    def offset_ms(self) -> int:
        return max(0, int((time.perf_counter() - self._start) * 1000))

    def elapsed_s(self) -> float:
        return time.perf_counter() - self._start

    def reset(self) -> None:
        self._start = time.perf_counter()


@runtime_checkable
class EventSink(Protocol):
    """Somewhere events go. Implementations must not raise; the bus isolates them anyway."""

    async def handle(self, event: ExecutionEvent) -> None: ...


class MemoryEventSink:
    """Keeps events in memory.

    Used by tests, by scenario assertions, and by the API for runs whose events have not yet
    been flushed to the database.
    """

    def __init__(self, max_events: int = 100_000) -> None:
        self.events: list[ExecutionEvent] = []
        self._max = max_events

    async def handle(self, event: ExecutionEvent) -> None:
        if len(self.events) < self._max:
            self.events.append(event)

    def for_run(self, run_id: str) -> list[ExecutionEvent]:
        return [e for e in self.events if e.run_id == run_id]

    def of_type(self, event_type: EventType) -> list[ExecutionEvent]:
        return [e for e in self.events if e.event_type is event_type]

    def clear(self) -> None:
        self.events.clear()


class StreamEventSink:
    """Fans events out to live subscribers. Consumed by SSE in Phase 19.

    Each subscriber gets its own bounded queue. A slow client drops events rather than
    stalling the run — the client can recover the gap by replaying from `Last-Event-ID`,
    so backpressure onto the agent would be the wrong trade.
    """

    def __init__(self, queue_size: int = 1000) -> None:
        self._subscribers: dict[str, list[asyncio.Queue[ExecutionEvent]]] = {}
        self._queue_size = queue_size

    def subscribe(self, run_id: str) -> asyncio.Queue[ExecutionEvent]:
        queue: asyncio.Queue[ExecutionEvent] = asyncio.Queue(maxsize=self._queue_size)
        self._subscribers.setdefault(run_id, []).append(queue)
        return queue

    def unsubscribe(self, run_id: str, queue: asyncio.Queue[ExecutionEvent]) -> None:
        queues = self._subscribers.get(run_id)
        if not queues:
            return
        if queue in queues:
            queues.remove(queue)
        if not queues:
            self._subscribers.pop(run_id, None)

    def subscriber_count(self, run_id: str) -> int:
        return len(self._subscribers.get(run_id, []))

    async def handle(self, event: ExecutionEvent) -> None:
        for queue in self._subscribers.get(event.run_id, []):
            try:
                queue.put_nowait(event)
            except asyncio.QueueFull:
                log.warning(
                    "stream_subscriber_lagging",
                    run_id=event.run_id,
                    dropped=event.event_type.value,
                )


class TraceFileSink:
    """Accumulates a run's events and writes a trace file when the run ends.

    Only active when `TRACE_TO_FILE=1`. Traces produced here are real recordings; nothing in
    this project ever hand-authors one.
    """

    _TERMINAL = frozenset({EventType.RUN_COMPLETED, EventType.RUN_FAILED, EventType.RUN_CANCELLED})

    def __init__(self, directory: Path | None = None, *, suffix: str = ".local.json") -> None:
        settings = get_settings()
        self.directory = directory or (settings.agent_dir / "traces")
        # Scratch traces are gitignored; curated ones are renamed deliberately.
        self.suffix = suffix
        self._buffers: dict[str, list[ExecutionEvent]] = {}
        self._objectives: dict[str, str] = {}

    async def handle(self, event: ExecutionEvent) -> None:
        self._buffers.setdefault(event.run_id, []).append(event)

        if event.event_type is EventType.RUN_STARTED:
            objective = event.payload.get("objective")
            if isinstance(objective, str):
                self._objectives[event.run_id] = objective

        if event.event_type in self._TERMINAL:
            self.flush(event.run_id, outcome=event.event_type.value)

    def flush(self, run_id: str, *, outcome: str = "") -> Path | None:
        events = self._buffers.pop(run_id, [])
        if not events:
            return None

        settings = get_settings()
        trace = ExecutionTrace(
            run_id=run_id,
            objective=self._objectives.pop(run_id, "(objective not recorded)"),
            model=settings.ollama_model,
            outcome=outcome,
            events=events,
        )

        self.directory.mkdir(parents=True, exist_ok=True)
        path = self.directory / f"{run_id}{self.suffix}"
        path.write_text(
            json.dumps(trace.model_dump(mode="json"), indent=2),
            encoding="utf-8",
        )
        log.info("trace_written", run_id=run_id, path=str(path), events=len(events))
        return path


class EventBus:
    """Dispatches events to sinks, with redaction and failure isolation."""

    def __init__(self, sinks: list[EventSink] | None = None) -> None:
        self._sinks: list[EventSink] = list(sinks or [])

    def subscribe(self, sink: EventSink) -> None:
        self._sinks.append(sink)

    def unsubscribe(self, sink: EventSink) -> None:
        if sink in self._sinks:
            self._sinks.remove(sink)

    @property
    def sink_count(self) -> int:
        return len(self._sinks)

    async def emit(self, event: ExecutionEvent) -> ExecutionEvent:
        """Redact, then dispatch to every sink. Returns the redacted event.

        Sinks run concurrently and their failures are swallowed with a log line. A sink that
        cannot write is a degraded observability path, not a reason to abandon an
        investigation.
        """
        clean = event.redacted()

        if not self._sinks:
            return clean

        results = await asyncio.gather(
            *(sink.handle(clean) for sink in self._sinks),
            return_exceptions=True,
        )
        for sink, result in zip(self._sinks, results, strict=True):
            if isinstance(result, BaseException):
                log.error(
                    "event_sink_failed",
                    sink=type(sink).__name__,
                    event_type=clean.event_type.value,
                    error=f"{type(result).__name__}: {result}",
                )
        return clean


class RunEventEmitter:
    """A bus handle bound to one run.

    Engines take one of these instead of a bus plus a run id plus a clock. Threading three
    things through ten components is how a transition eventually goes unrecorded.
    """

    def __init__(
        self,
        bus: EventBus,
        run_id: str,
        clock: RunClock | None = None,
    ) -> None:
        self.bus = bus
        self.run_id = run_id
        self.clock = clock or RunClock()
        self._revision = 0

    def set_revision(self, revision: int) -> None:
        """Tag subsequent events with the current replan iteration."""
        self._revision = revision

    async def emit(
        self,
        event_type: EventType,
        *,
        payload: JsonDict | None = None,
        task_id: str | None = None,
        finding_id: str | None = None,
        tool_name: str | None = None,
    ) -> ExecutionEvent:
        event = ExecutionEvent(
            run_id=self.run_id,
            event_type=event_type,
            t_offset_ms=self.clock.offset_ms(),
            payload=payload or {},
            task_id=task_id,
            finding_id=finding_id,
            tool_name=tool_name,
            revision=self._revision,
        )
        return await self.bus.emit(event)


def build_default_bus() -> tuple[EventBus, MemoryEventSink, StreamEventSink]:
    """The standard sink set for a local run.

    `DatabaseEventSink` is added in Phase 3, once the persistence layer exists. Until then a
    run's timeline lives in memory and, when `TRACE_TO_FILE=1`, in a trace file.
    """
    settings = get_settings()

    memory = MemoryEventSink()
    stream = StreamEventSink()
    sinks: list[EventSink] = [memory, stream]

    if settings.trace_to_file:
        sinks.append(TraceFileSink())

    return EventBus(sinks), memory, stream
