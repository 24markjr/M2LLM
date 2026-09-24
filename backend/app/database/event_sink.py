"""The database event sink — deferred since Phase 5, landing now.

Events are buffered and flushed in batches rather than written one at a time. A run emits
an event per state transition, and a round trip per transition would put database latency
inside the scheduling loop, where it would slow the agent down to no benefit.

The sink never raises. `EventBus` isolates sink failures already, but this one is
deliberately belt-and-braces: losing the record of an investigation is bad, and losing the
investigation to save the record would be worse.
"""

from __future__ import annotations

import asyncio

from app.core.logging import get_logger
from app.database.repositories import EventRepository
from app.database.session import session_scope
from app.schemas.event import EventType, ExecutionEvent

log = get_logger(__name__)

# Terminal events flush immediately: a run that ends should be durable at once, not
# whenever the buffer happens to fill.
_TERMINAL = frozenset({EventType.RUN_COMPLETED, EventType.RUN_FAILED, EventType.RUN_CANCELLED})


class DatabaseEventSink:
    """Persists the run timeline, in batches, without blocking the agent."""

    def __init__(self, *, batch_size: int = 25) -> None:
        self._buffer: list[ExecutionEvent] = []
        self._batch_size = batch_size
        self._lock = asyncio.Lock()
        self.dropped = 0

    async def handle(self, event: ExecutionEvent) -> None:
        async with self._lock:
            self._buffer.append(event)
            should_flush = len(self._buffer) >= self._batch_size or event.event_type in _TERMINAL
        if should_flush:
            await self.flush()

    async def flush(self) -> None:
        """Write buffered events. Failures are logged and counted, never raised."""
        async with self._lock:
            pending, self._buffer = self._buffer, []

        if not pending:
            return

        try:
            async with session_scope() as session:
                await EventRepository(session).append_many(pending)
        except Exception as exc:  # noqa: BLE001 - a sink must not kill a run
            self.dropped += len(pending)
            log.error(
                "event_persistence_failed",
                count=len(pending),
                dropped_total=self.dropped,
                error=f"{type(exc).__name__}: {exc}",
            )

    @property
    def buffered(self) -> int:
        return len(self._buffer)
