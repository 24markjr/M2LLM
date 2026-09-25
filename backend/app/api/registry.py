"""The run registry — missions in flight, and the event history that lets a client catch up.

The API never blocks on a run. `POST /missions` starts a background task and returns
immediately with a run id, because an investigation takes a minute or more and an HTTP
request that waits for one is a request that times out.

**History is kept per run, in order.** SSE reconnection replays from `Last-Event-ID`, and
that is only possible if the events a client missed still exist somewhere. `StreamEventSink`
deliberately drops events for a lagging subscriber rather than stalling the agent, so the
history is what makes that trade safe: the client recovers the gap instead of losing it.

This is in-memory and per-process. The database sink (Phase 3) is the durable record; this
exists so a live client can be served without a round trip to Postgres for every event.
"""

from __future__ import annotations

import asyncio
import itertools
from datetime import datetime

from app.api.persistence import persistence_enabled, record_finished, record_started
from app.api.recording import write_recording
from app.core.config import get_settings
from app.core.events import (
    EventBus,
    MemoryEventSink,
    RunEventEmitter,
    StreamEventSink,
)
from app.core.logging import get_logger
from app.database.event_sink import DatabaseEventSink
from app.orchestration.mission import MissionResult, MissionStatus, Stage, run_mission
from app.schemas.common import RunId, new_run_id, utcnow
from app.schemas.event import ExecutionEvent
from app.schemas.objective import Objective

log = get_logger(__name__)


class MissionRecord:
    """One mission: its result so far, its events, and the task running it."""

    # Monotonic creation order. `created_at` alone is not enough to sort by: two missions
    # created in the same millisecond tie, and the list order then varies between requests
    # for no reason the user can see.
    _sequence = itertools.count()

    def __init__(self, run_id: RunId, objective: Objective, documents: list[str]) -> None:
        self.sequence = next(MissionRecord._sequence)
        self.run_id = run_id
        self.objective = objective
        self.documents = documents
        self.created_at: datetime = utcnow()
        self.started_at: datetime | None = None
        self.finished_at: datetime | None = None

        self.status = MissionStatus.PENDING
        self.stage = Stage.UNDERSTANDING
        self.result: MissionResult | None = None
        self.task: asyncio.Task[None] | None = None
        self.events: list[ExecutionEvent] = []

    def is_finished(self) -> bool:
        """Whether the run has reached a terminal status.

        A method rather than a property because it changes under the caller: the SSE stream
        checks it repeatedly while the run proceeds, and a property would let a type checker
        narrow the first check and treat the rest as dead code.
        """
        return self.status in {
            MissionStatus.COMPLETED,
            MissionStatus.FAILED,
            MissionStatus.CANCELLED,
            MissionStatus.CLARIFICATION_NEEDED,
        }

    def events_after(self, last_event_id: str | None) -> list[ExecutionEvent]:
        """Events the client has not seen, in order.

        An unknown id replays everything rather than nothing. A client reconnecting with an
        id this process never issued - after a restart, say - would otherwise sit waiting
        for events that already happened, which is the one outcome worse than a duplicate.
        """
        if last_event_id is None:
            return list(self.events)
        for index, event in enumerate(self.events):
            if event.event_id == last_event_id:
                return self.events[index + 1 :]
        log.warning("unknown_last_event_id", run_id=self.run_id, last_event_id=last_event_id)
        return list(self.events)


class MissionRegistry:
    """Owns every mission this process is running or has run."""

    def __init__(self) -> None:
        self._missions: dict[RunId, MissionRecord] = {}
        self._stream = StreamEventSink()
        self._max_concurrent = get_settings().max_concurrent_runs
        self._running = 0
        # Created lazily in `create`, because availability is an async question and a registry is
        # constructed synchronously.
        self._database: DatabaseEventSink | None = None

    # --- reading -----------------------------------------------------------

    def get(self, run_id: str) -> MissionRecord | None:
        return self._missions.get(run_id)

    def records(self) -> list[MissionRecord]:
        """Newest first: a mission list is read from the top."""
        return sorted(self._missions.values(), key=lambda m: m.sequence, reverse=True)

    @property
    def stream(self) -> StreamEventSink:
        return self._stream

    @property
    def at_capacity(self) -> bool:
        return self._running >= self._max_concurrent

    # --- writing -----------------------------------------------------------

    async def create(
        self,
        *,
        objective: Objective,
        documents: list[str],
        loaded: dict[str, str],
        page_starts: dict[str, list[int]],
        provider: object,
    ) -> MissionRecord:
        """Register a mission and start it. Returns as soon as the task is scheduled.

        Async only to probe the database once: attaching a sink that cannot write would log a
        failed connection on every flush, and a log full of expected errors is a log nobody reads.
        """
        record = MissionRecord(new_run_id(), objective, documents)
        self._missions[record.run_id] = record

        history = _HistorySink(record)
        memory = MemoryEventSink()
        sinks: list[object] = [history, memory, self._stream]

        # The durable timeline, when a database is reachable. One more sink rather than a
        # replacement: the in-memory history is what serves SSE replay without a round trip to
        # Postgres per event, and the two answer different questions.
        #
        if await persistence_enabled():
            if self._database is None:
                self._database = DatabaseEventSink()
            sinks.append(self._database)

        emitter = RunEventEmitter(EventBus(sinks), record.run_id)  # type: ignore[arg-type]

        record.task = asyncio.create_task(
            self._run(record, emitter, loaded, page_starts, provider),
            name=f"mission-{record.run_id}",
        )
        return record

    async def cancel(self, record: MissionRecord) -> bool:
        """Ask a running mission to stop. False if it had already finished."""
        if record.is_finished() or record.task is None:
            return False
        return bool(record.task.cancel())

    async def _run(
        self,
        record: MissionRecord,
        emitter: RunEventEmitter,
        documents: dict[str, str],
        page_starts: dict[str, list[int]],
        provider: object,
    ) -> None:
        from app.llm.provider import LLMProvider

        assert isinstance(provider, LLMProvider)

        record.status = MissionStatus.RUNNING
        record.started_at = utcnow()
        self._running += 1

        # The run row has to exist before any event references it.
        await record_started(record)

        async def on_stage(stage: Stage, result: MissionResult) -> None:
            # Keeps the mission's phase queryable while the run is still going, so a client
            # that polls instead of streaming still sees where it is.
            record.stage = stage
            record.status = result.status

        try:
            record.result = await run_mission(
                objective=record.objective,
                documents=documents,
                provider=provider,
                emitter=emitter,
                page_starts=page_starts,
                on_stage=on_stage,
            )
            record.status = record.result.status
        except asyncio.CancelledError:
            record.status = MissionStatus.CANCELLED
            log.info("mission_cancelled", run_id=record.run_id)
        finally:
            self._running -= 1
            record.stage = Stage.DONE
            record.finished_at = utcnow()
            # Recorded on the way out, so a run that failed or was cancelled is replayable
            # too. A recording of only the successful runs would make the demo look better
            # than the system is.
            write_recording(record)
            if self._database is not None:
                # Flush before the final write, so the stored timeline is complete when the run
                # row is marked finished.
                await self._database.flush()
            await record_finished(record)


class _HistorySink:
    """Appends every event to a mission's history, so SSE can replay it."""

    def __init__(self, record: MissionRecord) -> None:
        self._record = record

    async def handle(self, event: ExecutionEvent) -> None:
        self._record.events.append(event)


_registry: MissionRegistry | None = None


def get_registry() -> MissionRegistry:
    global _registry
    if _registry is None:
        _registry = MissionRegistry()
    return _registry


def reset_registry() -> None:
    """Drop all state. For tests: a registry that leaks between them is a shared fixture."""
    global _registry
    _registry = None
