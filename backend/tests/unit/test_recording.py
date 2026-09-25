"""Phase 22 — recordings, and what a replay is allowed to claim.

A recording exists so a demo does not depend on a local model behaving on the day. That is only
honest if two things hold: the recording came out of a real run, and the replay is disclosed as a
replay. The first is what these tests are about.

The second is the UI's job (`frontend/src/pages/pages.tsx` renders a non-dismissible banner).
"""

from __future__ import annotations

import json

import pytest
from httpx import ASGITransport, AsyncClient

from app.api.app import create_app
from app.api.recording import list_recordings, load_recording, recordings_dir, write_recording
from app.api.registry import MissionRecord, reset_registry
from app.core.events import EventBus, RunEventEmitter
from app.orchestration.mission import MissionStatus
from app.schemas.common import new_run_id
from app.schemas.event import EventType
from app.schemas.objective import Objective


@pytest.fixture(autouse=True)
def _clean(tmp_path, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    """Point recordings at a temp directory. A test that writes into `.agent/traces/` would
    leave artefacts that look like real recordings of runs that never happened."""
    reset_registry()
    monkeypatch.setattr("app.api.recording.recordings_dir", lambda: tmp_path / "traces")


async def _record(
    status: MissionStatus = MissionStatus.COMPLETED, events: int = 3
) -> MissionRecord:
    from app.api.registry import _HistorySink

    record = MissionRecord(new_run_id(), Objective(text="Check the reports."), ["report.txt"])
    record.status = status
    emitter = RunEventEmitter(EventBus([_HistorySink(record)]), record.run_id)
    for index in range(events):
        await emitter.emit(EventType.TASK_STARTED, payload={"n": index})
    return record


# --- writing --------------------------------------------------------------------


async def test_a_run_with_no_events_records_nothing() -> None:
    """An empty file would appear in the picker as a replayable run that has nothing to show."""
    record = MissionRecord(new_run_id(), Objective(text="Check."), [])
    assert write_recording(record) is None


async def test_a_recording_holds_the_events_and_the_final_state() -> None:
    """Events give the timing, the snapshot gives the content.

    Event payloads are summaries - a truncated claim, a rounded confidence - so a replay driven
    by events alone could animate the graph but never drill into a finding's evidence.
    """
    record = await _record()
    path = write_recording(record)

    assert path is not None
    raw = json.loads(path.read_text(encoding="utf-8"))
    assert len(raw["events"]) == 3
    assert "snapshot" in raw
    assert raw["snapshot"]["mission"]["run_id"] == record.run_id
    assert raw["outcome"] == "COMPLETED"


async def test_a_failed_run_is_recorded_too() -> None:
    """Recording only the successful runs would make the demo look better than the system is."""
    record = await _record(status=MissionStatus.FAILED)
    path = write_recording(record)

    assert path is not None
    assert json.loads(path.read_text(encoding="utf-8"))["outcome"] == "FAILED"


async def test_recording_never_raises_into_the_run() -> None:
    """The caller is a `finally` block on the mission task. Losing a recording is a lost demo
    aid; raising here would lose a run that had already produced its findings."""
    record = await _record()
    record.objective = None  # type: ignore[assignment] - force a failure inside

    assert write_recording(record) is None


async def test_scratch_recordings_are_marked_as_not_committed() -> None:
    """A committed recording is a considered act, not whatever ran last."""
    write_recording(await _record())
    rows = list_recordings()

    assert len(rows) == 1
    assert rows[0]["committed"] is False
    assert rows[0]["file"].endswith(".local.json")


# --- reading --------------------------------------------------------------------


async def test_a_recording_round_trips() -> None:
    record = await _record(events=4)
    write_recording(record)

    loaded = load_recording(f"{record.run_id}.local.json")

    assert loaded is not None
    assert loaded["run_id"] == record.run_id
    assert len(loaded["events"]) == 4


def test_a_traversal_attempt_reads_nothing() -> None:
    """The name comes from a URL. `..` in a filename is the oldest way to read a file the API
    was never meant to serve."""
    assert load_recording("../../../.env") is None
    assert load_recording("..\\..\\secrets.json") is None


def test_an_unreadable_recording_is_skipped_not_fatal() -> None:
    """One corrupt file must not empty the whole picker."""
    directory = recordings_dir()
    directory.mkdir(parents=True, exist_ok=True)
    (directory / "broken.local.json").write_text("{not json", encoding="utf-8")

    assert list_recordings() == []


# --- the routes -----------------------------------------------------------------


async def test_the_api_lists_and_serves_recordings() -> None:
    record = await _record()
    write_recording(record)

    async with AsyncClient(
        transport=ASGITransport(app=create_app()), base_url="http://test"
    ) as client:
        listing = await client.get("/api/v1/recordings")
        assert listing.status_code == 200
        rows = listing.json()
        assert len(rows) == 1

        full = await client.get(f"/api/v1/recordings/{rows[0]['file']}")
        assert full.status_code == 200
        assert len(full.json()["events"]) == 3


async def test_a_missing_recording_returns_a_code() -> None:
    async with AsyncClient(
        transport=ASGITransport(app=create_app()), base_url="http://test"
    ) as client:
        response = await client.get("/api/v1/recordings/nope.json")

    assert response.status_code == 404
    assert response.json()["error_code"] == "RECORDING_NOT_FOUND"


async def test_metric_directions_are_served_not_assumed() -> None:
    """The direction of a metric is a property of the metric. A frontend holding its own copy
    would eventually colour a rising unsupported_claim_rate green."""
    async with AsyncClient(
        transport=ASGITransport(app=create_app()), base_url="http://test"
    ) as client:
        directions = (await client.get("/api/v1/evaluation/directions")).json()

    assert directions["unsupported_claim_rate"] == "lower"
    assert directions["task_efficiency"] == "lower"
    assert directions["evidence_coverage"] == "higher"


async def test_the_snapshot_matches_what_the_live_routes_serve() -> None:
    """The claim a replay makes is that it renders what the live view rendered.

    That holds only while the snapshot is built from the same shapers the routes use. If the two
    ever diverge, a replay stops being a faithful rendering of the run and becomes a second
    implementation of one - which would look right and be wrong, the worst combination.
    """
    from app.api.recording import _snapshot
    from app.api.registry import get_registry

    record = await _record()
    registry = get_registry()
    registry._missions[record.run_id] = record

    snapshot = _snapshot(record)

    async with AsyncClient(
        transport=ASGITransport(app=create_app()), base_url="http://test"
    ) as client:
        live = (await client.get(f"/api/v1/missions/{record.run_id}")).json()

    assert snapshot["mission"] == live, "a replay would render something no live view produced"
