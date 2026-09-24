"""Phase 19 — the HTTP surface.

Two things are worth testing hard here, and neither is a route returning 200.

**The error contract.** Every failure carries an `error_code` the frontend branches on. A
response that returns a bare string, or FastAPI's default validation body, is a response the
client has to parse prose out of.

**SSE reconnection.** A client that drops mid-run reconnects with `Last-Event-ID` and must
get exactly what it missed: no gap, no duplicate. That is the whole reason for choosing SSE
(ADR-008), so it is the thing that has to hold.

The provider is an `EchoProvider` throughout. These tests are about the HTTP layer, and
routing them through a real model would make them slow and non-deterministic without testing
anything the intelligence tests do not already cover.
"""

from __future__ import annotations

import asyncio
import json

import pytest
from httpx import ASGITransport, AsyncClient

from app.api.app import create_app
from app.api.registry import MissionRecord, get_registry, reset_registry
from app.core.events import EventBus, RunEventEmitter
from app.orchestration.mission import MissionStatus, Stage
from app.schemas.common import new_run_id
from app.schemas.event import EventType
from app.schemas.objective import Objective


@pytest.fixture(autouse=True)
def _clean_registry() -> None:
    """A registry that leaks between tests is a shared fixture pretending to be isolation."""
    reset_registry()


async def _client() -> AsyncClient:
    app = create_app()
    return AsyncClient(transport=ASGITransport(app=app), base_url="http://test")


def _record(status: MissionStatus = MissionStatus.RUNNING) -> MissionRecord:
    """Register a mission without running it, so routes can be tested in isolation."""
    registry = get_registry()
    record = MissionRecord(new_run_id(), Objective(text="Check the reports."), ["report.txt"])
    record.status = status
    registry._missions[record.run_id] = record
    return record


async def _emit(record: MissionRecord, count: int) -> list[str]:
    """Append real events to a mission's history and return their ids."""
    from app.api.registry import _HistorySink

    sink = _HistorySink(record)
    emitter = RunEventEmitter(EventBus([sink]), record.run_id)
    for index in range(count):
        await emitter.emit(EventType.TASK_STARTED, payload={"n": index})
    return [e.event_id for e in record.events]


# --- the error contract ---------------------------------------------------------


async def test_a_missing_mission_returns_a_code_not_a_string() -> None:
    async with await _client() as client:
        response = await client.get("/api/v1/missions/run_does_not_exist")

    assert response.status_code == 404
    body = response.json()
    assert body["error_code"] == "MISSION_NOT_FOUND"
    assert body["run_id"] == "run_does_not_exist"


async def test_a_malformed_body_still_carries_an_error_code() -> None:
    """FastAPI's default validation response has no code, so a client cannot branch on it."""
    async with await _client() as client:
        response = await client.post("/api/v1/missions", json={"objective": "short"})

    assert response.status_code == 422
    assert response.json()["error_code"] == "INVALID_REQUEST"


async def test_asking_for_a_report_before_it_exists_is_a_conflict_not_a_404() -> None:
    """409 tells the client to retry. 404 would tell it to give up on a report that is
    still being written."""
    record = _record()
    record.stage = Stage.EXECUTING

    async with await _client() as client:
        response = await client.get(f"/api/v1/missions/{record.run_id}/report")

    assert response.status_code == 409
    body = response.json()
    assert body["error_code"] == "MISSION_NOT_FINISHED"
    assert body["details"]["stage"] == "EXECUTING"


async def test_an_unreadable_document_set_is_refused_before_a_run_starts() -> None:
    """Starting a run against nothing readable would produce a plan and no investigation."""
    async with await _client() as client:
        response = await client.post(
            "/api/v1/missions",
            json={"objective": "Investigate the missing reports.", "documents": ["ghost.txt"]},
        )

    assert response.status_code == 422
    assert response.json()["error_code"] == "NO_READABLE_DOCUMENTS"


# --- listing and detail ---------------------------------------------------------


async def test_missions_are_listed_newest_first() -> None:
    first = _record()
    second = _record()

    async with await _client() as client:
        response = await client.get("/api/v1/missions")

    assert response.status_code == 200
    ids = [m["run_id"] for m in response.json()]
    assert ids[:2] == [second.run_id, first.run_id]


async def test_detail_reports_the_stage_while_the_run_is_still_going() -> None:
    """A client that polls instead of streaming still needs to know where the run is."""
    record = _record()
    record.stage = Stage.REASONING

    async with await _client() as client:
        response = await client.get(f"/api/v1/missions/{record.run_id}")

    body = response.json()
    assert body["stage"] == "REASONING"
    assert body["status"] == "RUNNING"
    assert body["has_report"] is False


async def test_the_event_log_paginates() -> None:
    record = _record()
    await _emit(record, 5)

    async with await _client() as client:
        response = await client.get(
            f"/api/v1/missions/{record.run_id}/events", params={"offset": 2, "limit": 2}
        )

    body = response.json()
    assert body["total"] == 5
    assert len(body["events"]) == 2
    assert body["offset"] == 2
    assert all(e["event_type"] == "TASK_STARTED" for e in body["events"])


async def test_events_carry_the_offset_that_builds_a_timeline() -> None:
    """`t_offset_ms` is what produces a relative timeline. Wall-clock would make every
    trace incomparable to every other."""
    record = _record()
    await _emit(record, 2)

    async with await _client() as client:
        response = await client.get(f"/api/v1/missions/{record.run_id}/events")

    for event in response.json()["events"]:
        assert "t_offset_ms" in event
        assert event["t_offset_ms"] >= 0


# --- SSE: the reconnection contract ---------------------------------------------


async def test_the_stream_replays_only_what_the_client_missed() -> None:
    """The headline SSE guarantee: reconnect with no gap and no duplicate."""
    record = _record(MissionStatus.COMPLETED)
    ids = await _emit(record, 4)

    async with await _client() as client:
        response = await client.get(
            f"/api/v1/missions/{record.run_id}/stream",
            headers={"Last-Event-ID": ids[1]},
        )

    assert response.status_code == 200
    delivered = _ids_in(response.text)
    assert delivered == ids[2:], "the client got exactly the events after the one it had"


async def test_an_unknown_last_event_id_replays_everything() -> None:
    """After a restart the id the client holds was issued by a process that is gone. Sitting
    silent would leave it waiting for events that already happened - worse than a duplicate.
    """
    record = _record(MissionStatus.COMPLETED)
    ids = await _emit(record, 3)

    async with await _client() as client:
        response = await client.get(
            f"/api/v1/missions/{record.run_id}/stream",
            headers={"Last-Event-ID": "evt_from_a_previous_process"},
        )

    assert _ids_in(response.text) == ids


async def test_a_finished_run_closes_the_stream_instead_of_hanging() -> None:
    """An SSE client reconnects automatically when a stream ends. A run that finished without
    saying so produces a reconnect loop against a mission that will never emit again."""
    record = _record(MissionStatus.COMPLETED)
    await _emit(record, 1)

    async with await _client() as client:
        response = await client.get(f"/api/v1/missions/{record.run_id}/stream")

    assert "event: stream_closed" in response.text
    closing = json.loads(response.text.rsplit("data: ", 1)[1].strip())
    assert closing["status"] == "COMPLETED"


async def test_stream_frames_carry_an_id_and_a_type() -> None:
    """`id:` is what the client echoes back; `event:` lets it attach a listener per kind
    rather than switching on a field inside the JSON."""
    record = _record(MissionStatus.COMPLETED)
    await _emit(record, 1)

    async with await _client() as client:
        response = await client.get(f"/api/v1/missions/{record.run_id}/stream")

    assert "id: " in response.text
    assert "event: TASK_STARTED" in response.text
    assert response.headers["content-type"].startswith("text/event-stream")
    assert response.headers["x-accel-buffering"] == "no"


async def test_the_stream_does_not_leak_a_subscriber() -> None:
    """Every connection subscribes to the run's queue. One that never unsubscribes is an
    event queue that fills forever behind a client that left."""
    record = _record(MissionStatus.COMPLETED)
    await _emit(record, 1)

    async with await _client() as client:
        await client.get(f"/api/v1/missions/{record.run_id}/stream")

    assert get_registry().stream.subscriber_count(record.run_id) == 0


# --- cancellation ---------------------------------------------------------------


async def test_cancelling_a_finished_mission_reports_that_it_did_nothing() -> None:
    record = _record(MissionStatus.COMPLETED)

    async with await _client() as client:
        response = await client.post(f"/api/v1/missions/{record.run_id}/cancel")

    assert response.status_code == 202
    assert response.json()["cancelling"] is False


async def test_cancelling_a_running_mission_is_accepted() -> None:
    """202, not 200: cancellation is cooperative, so it is requested rather than done."""
    record = _record()

    async def _forever() -> None:
        await asyncio.sleep(3600)

    record.task = asyncio.create_task(_forever())
    try:
        async with await _client() as client:
            response = await client.post(f"/api/v1/missions/{record.run_id}/cancel")

        assert response.status_code == 202
        assert response.json()["cancelling"] is True
    finally:
        record.task.cancel()


# --- capacity -------------------------------------------------------------------


async def test_the_api_refuses_rather_than_queueing_invisibly() -> None:
    """A local model serves one request at a time. An accepted-but-queued mission would sit
    at PENDING with no indication of why, looking exactly like one that had hung."""
    registry = get_registry()
    registry._running = registry._max_concurrent

    async with await _client() as client:
        response = await client.post(
            "/api/v1/missions", json={"objective": "Investigate the Aurora reports."}
        )

    assert response.status_code == 429
    assert response.json()["error_code"] == "AT_CAPACITY"


# --- health ---------------------------------------------------------------------


async def test_health_reports_the_model_not_just_a_status() -> None:
    """A 200 that does not name the model cannot distinguish a working engine from one
    pointed at a model that is not installed."""
    async with await _client() as client:
        response = await client.get("/health")

    body = response.json()
    assert response.status_code == 200
    assert body["model"]
    assert "provider_healthy" in body


def _ids_in(text: str) -> list[str]:
    """Pull the `id:` lines out of an SSE body, in order."""
    return [
        line.removeprefix("id: ").strip() for line in text.splitlines() if line.startswith("id: ")
    ]
