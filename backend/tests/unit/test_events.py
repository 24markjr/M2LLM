"""Phase 5 — event bus, redaction, and sink isolation."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path

import pytest

from app.core.events import (
    EventBus,
    MemoryEventSink,
    RunClock,
    RunEventEmitter,
    StreamEventSink,
    TraceFileSink,
)
from app.schemas.common import new_run_id
from app.schemas.event import EventType, ExecutionEvent


class ExplodingSink:
    """A sink that always fails. Used to prove failures stay contained."""

    def __init__(self) -> None:
        self.calls = 0

    async def handle(self, event: ExecutionEvent) -> None:
        self.calls += 1
        raise RuntimeError("disk on fire")


# --- redaction: invariant #3 ---------------------------------------------------


async def test_model_deliberation_never_reaches_a_sink() -> None:
    """The enforcement point for 'no hidden chain-of-thought'.

    A component may put raw completion text in a payload while debugging. It must not
    survive to storage, the stream, or a trace file.
    """
    memory = MemoryEventSink()
    bus = EventBus([memory])

    await bus.emit(
        ExecutionEvent(
            run_id=new_run_id(),
            event_type=EventType.FINDING_CREATED,
            t_offset_ms=100,
            payload={
                "finding_id": "F-001",
                "raw_response": "step 1, I should consider...",
                "prompt": "You are an investigator...",
                "chain_of_thought": "hmm",
            },
        )
    )

    stored = memory.events[0].payload
    assert stored == {"finding_id": "F-001"}


async def test_redaction_leaves_clean_payloads_untouched() -> None:
    memory = MemoryEventSink()
    bus = EventBus([memory])
    payload = {"task_id": "task_001", "tool": "document_search", "results": 3}

    await bus.emit(
        ExecutionEvent(
            run_id=new_run_id(),
            event_type=EventType.TOOL_EXECUTED,
            t_offset_ms=50,
            payload=payload,
        )
    )
    assert memory.events[0].payload == payload


# --- sink isolation ------------------------------------------------------------


async def test_a_failing_sink_does_not_kill_the_run() -> None:
    """Losing a trace file is an inconvenience. Losing the investigation is not."""
    exploding = ExplodingSink()
    memory = MemoryEventSink()
    bus = EventBus([exploding, memory])

    await bus.emit(
        ExecutionEvent(run_id=new_run_id(), event_type=EventType.RUN_STARTED, t_offset_ms=0)
    )

    assert exploding.calls == 1
    assert len(memory.events) == 1, "the healthy sink still received the event"


async def test_emit_works_with_no_sinks() -> None:
    bus = EventBus()
    event = await bus.emit(
        ExecutionEvent(run_id=new_run_id(), event_type=EventType.RUN_STARTED, t_offset_ms=0)
    )
    assert event.event_type is EventType.RUN_STARTED


# --- clock and emitter ---------------------------------------------------------


def test_clock_offsets_are_monotonic_and_non_negative() -> None:
    clock = RunClock()
    first = clock.offset_ms()
    second = clock.offset_ms()
    assert 0 <= first <= second


async def test_emitter_binds_run_id_and_revision() -> None:
    """Engines take an emitter, not a bus plus a run id plus a clock.

    Threading three things through ten components is how a transition eventually goes
    unrecorded.
    """
    memory = MemoryEventSink()
    bus = EventBus([memory])
    run_id = new_run_id()
    emitter = RunEventEmitter(bus, run_id)

    await emitter.emit(EventType.RUN_STARTED)
    emitter.set_revision(2)
    await emitter.emit(EventType.TASK_CREATED, task_id="task_009")

    assert [e.run_id for e in memory.events] == [run_id, run_id]
    assert memory.events[0].revision == 0
    assert memory.events[1].revision == 2
    assert memory.events[1].task_id == "task_009"


async def test_emitter_produces_an_ordered_timeline() -> None:
    memory = MemoryEventSink()
    emitter = RunEventEmitter(EventBus([memory]), new_run_id())

    for event_type in (
        EventType.RUN_STARTED,
        EventType.INTENT_CREATED,
        EventType.PLAN_CREATED,
        EventType.RUN_COMPLETED,
    ):
        await emitter.emit(event_type)

    offsets = [e.t_offset_ms for e in memory.events]
    assert offsets == sorted(offsets), "the timeline must be monotonic"


# --- stream sink (SSE, Phase 19) -----------------------------------------------


async def test_stream_sink_delivers_only_to_that_run() -> None:
    stream = StreamEventSink()
    bus = EventBus([stream])
    run_a, run_b = new_run_id(), new_run_id()

    queue = stream.subscribe(run_a)
    await bus.emit(ExecutionEvent(run_id=run_b, event_type=EventType.RUN_STARTED, t_offset_ms=0))
    await bus.emit(ExecutionEvent(run_id=run_a, event_type=EventType.RUN_STARTED, t_offset_ms=0))

    received = queue.get_nowait()
    assert received.run_id == run_a
    assert queue.empty()


async def test_a_slow_subscriber_drops_events_rather_than_stalling_the_run() -> None:
    """Backpressure onto the agent would be the wrong trade.

    A lagging client recovers its gap by replaying from Last-Event-ID; a stalled
    investigation does not recover at all.
    """
    stream = StreamEventSink(queue_size=1)
    bus = EventBus([stream])
    run_id = new_run_id()
    stream.subscribe(run_id)

    for i in range(5):
        await asyncio.wait_for(
            bus.emit(
                ExecutionEvent(run_id=run_id, event_type=EventType.TASK_STARTED, t_offset_ms=i)
            ),
            timeout=1.0,
        )


async def test_unsubscribe_removes_the_queue() -> None:
    stream = StreamEventSink()
    run_id = new_run_id()
    queue = stream.subscribe(run_id)
    assert stream.subscriber_count(run_id) == 1

    stream.unsubscribe(run_id, queue)
    assert stream.subscriber_count(run_id) == 0


# --- trace file sink -----------------------------------------------------------


async def test_trace_file_is_written_when_the_run_ends(tmp_path: Path) -> None:
    sink = TraceFileSink(directory=tmp_path, suffix=".json")
    bus = EventBus([sink])
    run_id = new_run_id()

    await bus.emit(
        ExecutionEvent(
            run_id=run_id,
            event_type=EventType.RUN_STARTED,
            t_offset_ms=0,
            payload={"objective": "Find inconsistencies."},
        )
    )
    await bus.emit(
        ExecutionEvent(run_id=run_id, event_type=EventType.EVIDENCE_GAP_DETECTED, t_offset_ms=6900)
    )
    await bus.emit(
        ExecutionEvent(run_id=run_id, event_type=EventType.RUN_COMPLETED, t_offset_ms=9520)
    )

    path = tmp_path / f"{run_id}.json"
    assert path.exists()

    trace = json.loads(path.read_text(encoding="utf-8"))
    assert trace["run_id"] == run_id
    assert trace["objective"] == "Find inconsistencies."
    assert trace["outcome"] == "RUN_COMPLETED"
    assert len(trace["events"]) == 3


async def test_trace_records_redacted_events_only(tmp_path: Path) -> None:
    """A trace is a published artifact. Deliberation must not leak into it."""
    sink = TraceFileSink(directory=tmp_path, suffix=".json")
    bus = EventBus([sink])
    run_id = new_run_id()

    await bus.emit(
        ExecutionEvent(
            run_id=run_id,
            event_type=EventType.RUN_STARTED,
            t_offset_ms=0,
            payload={"objective": "o", "system_prompt": "secret instructions"},
        )
    )
    await bus.emit(
        ExecutionEvent(run_id=run_id, event_type=EventType.RUN_COMPLETED, t_offset_ms=10)
    )

    raw = (tmp_path / f"{run_id}.json").read_text(encoding="utf-8")
    assert "secret instructions" not in raw


async def test_no_trace_is_written_for_a_run_with_no_events(tmp_path: Path) -> None:
    sink = TraceFileSink(directory=tmp_path, suffix=".json")
    assert sink.flush("run_aaaaaaaaaaaa") is None


# --- memory sink views ---------------------------------------------------------


async def test_memory_sink_filters_by_run_and_type() -> None:
    memory = MemoryEventSink()
    bus = EventBus([memory])
    run_a, run_b = new_run_id(), new_run_id()

    await bus.emit(ExecutionEvent(run_id=run_a, event_type=EventType.TASK_STARTED, t_offset_ms=1))
    await bus.emit(ExecutionEvent(run_id=run_b, event_type=EventType.TASK_STARTED, t_offset_ms=2))
    await bus.emit(ExecutionEvent(run_id=run_a, event_type=EventType.TASK_COMPLETED, t_offset_ms=3))

    assert len(memory.for_run(run_a)) == 2
    assert len(memory.of_type(EventType.TASK_STARTED)) == 2


@pytest.mark.parametrize(
    "event_type",
    [EventType.RUN_COMPLETED, EventType.RUN_FAILED, EventType.RUN_CANCELLED],
)
async def test_every_terminal_outcome_flushes_a_trace(
    tmp_path: Path, event_type: EventType
) -> None:
    """A failed or cancelled run is exactly the one worth having a trace of."""
    sink = TraceFileSink(directory=tmp_path, suffix=".json")
    bus = EventBus([sink])
    run_id = new_run_id()

    await bus.emit(ExecutionEvent(run_id=run_id, event_type=EventType.RUN_STARTED, t_offset_ms=0))
    await bus.emit(ExecutionEvent(run_id=run_id, event_type=event_type, t_offset_ms=500))

    assert (tmp_path / f"{run_id}.json").exists()
