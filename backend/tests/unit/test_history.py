"""Phase U1: investigations survive a restart; run history as records; deletion that is recorded."""

from __future__ import annotations

import pytest
from httpx import ASGITransport, AsyncClient

from app.api import archive
from app.api.app import create_app
from app.api.registry import MissionRecord, get_registry, reset_registry
from app.intelligence.challenge import ChallengeOutcome, ChallengeResult
from app.orchestration.mission import MissionResult, MissionStatus, Stage
from app.schemas.common import SourceLocator, new_run_id
from app.schemas.evidence import EvidenceRef, ResolutionStatus
from app.schemas.finding import Finding
from app.schemas.objective import Objective
from app.schemas.verification import VerificationResult, VerificationStatus


@pytest.fixture(autouse=True)
def _clean_registry() -> None:
    """Each test starts with no investigations: other modules leave theirs in the registry."""
    reset_registry()


def _finished(objective: str = "Does the budget exceed its approval?") -> MissionRecord:
    finding = Finding(
        finding_id="F-001",
        claim="Spend of 287,500 exceeds the approved 250,000.",
        evidence=[
            EvidenceRef(
                evidence_id="E-001",
                locator=SourceLocator(document_id="ledger.txt", row=3),
                resolution=ResolutionStatus.RESOLVED,
            )
        ],
        verification=VerificationResult(status=VerificationStatus.SUPPORTED, confidence=0.9),
    )
    record = MissionRecord(new_run_id(), Objective(text=objective), ["ledger.txt"])
    record.status, record.stage = MissionStatus.COMPLETED, Stage.DONE
    record.texts = {"ledger.txt": "a\nb\nSpend 287,500 against 250,000 approved."}
    record.case_id = "CASE-2026-00001"
    record.result = MissionResult(
        run_id=record.run_id, objective=record.objective, findings=[finding]
    )
    get_registry()._missions[record.run_id] = record
    return record


async def _client() -> AsyncClient:
    return AsyncClient(transport=ASGITransport(app=create_app()), base_url="http://test")


# --- U1a: an investigation survives a restart -----------------------------------------------------


async def test_a_finished_investigation_is_back_after_a_restart() -> None:
    record = _finished()
    assert archive.write_archive(record) is not None
    run_id = record.run_id

    reset_registry()  # the process restarts: nothing in memory
    async with await _client() as client:
        listed = (await client.get("/api/v1/missions")).json()
        findings = (await client.get(f"/api/v1/missions/{run_id}/findings")).json()
        detail = (await client.get(f"/api/v1/missions/{run_id}")).json()

    assert [m["run_id"] for m in listed] == [run_id]
    assert findings["findings"][0]["claim"].startswith("Spend of 287,500")
    assert detail["status"] == "COMPLETED"
    restored = get_registry().get(run_id)
    assert restored is not None and restored.case_id == "CASE-2026-00001"
    assert restored.texts["ledger.txt"].endswith("approved."), "the text it read, not a re-read"


def test_a_running_mission_is_not_archived() -> None:
    record = _finished()
    record.status = MissionStatus.RUNNING
    assert archive.write_archive(record) is None


def test_a_challenge_is_kept_with_the_run() -> None:
    record = _finished()
    record.challenges["F-001"] = ChallengeResult(
        finding_id="F-001",
        claim="x",
        outcome=ChallengeOutcome.WITHSTOOD,
        summary="nothing disagrees",
    )
    archive.write_archive(record)
    reset_registry()
    restored = get_registry().get(record.run_id)
    assert restored is not None
    assert restored.challenges["F-001"].outcome is ChallengeOutcome.WITHSTOOD


def test_a_broken_archive_is_skipped_not_fatal() -> None:
    record = _finished()
    archive.write_archive(record)
    archive.archives_dir().joinpath("run_000000000000.json").write_text("{", encoding="utf-8")
    reset_registry()
    assert [r.run_id for r in get_registry().records()] == [record.run_id]


def test_restored_runs_sort_before_new_ones() -> None:
    older = _finished("first")
    archive.write_archive(older)
    reset_registry()
    newer = MissionRecord(new_run_id(), Objective(text="second"), [])
    registry = get_registry()
    registry.records()  # restores
    registry._missions[newer.run_id] = newer
    assert [r.objective.text for r in registry.records()] == ["second", "first"]


# --- U1b: recordings as records, and deleting them ------------------------------------------------


def _recording(name: str, run_id: str, outcome: str, findings: int, at: str) -> None:
    import json

    from app.api.recording import recordings_dir

    directory = recordings_dir()
    directory.mkdir(parents=True, exist_ok=True)
    body = {
        "run_id": run_id,
        "objective": f"objective of {run_id}",
        "outcome": outcome,
        "recorded_at": at,
        "events": [{"t_offset_ms": 0}, {"t_offset_ms": 5000}],
        "snapshot": {"mission": {"finding_count": findings, "case_id": "CASE-2026-00002"}},
    }
    (directory / name).write_text(json.dumps(body), encoding="utf-8")


def _three_recordings() -> None:
    _recording("run_aaaaaaaaaaaa.local.json", "run_aaaaaaaaaaaa", "COMPLETED", 2, "2026-10-13T01")
    _recording("run_bbbbbbbbbbbb.local.json", "run_bbbbbbbbbbbb", "FAILED", 0, "2026-10-13T02")
    _recording("aurora-demo.json", "run_cccccccccccc", "COMPLETED", 3, "2026-10-13T03")
    _recording("run_cccccccccccc.local.json", "run_cccccccccccc", "COMPLETED", 3, "2026-10-13T04")


async def test_the_default_list_hides_empty_and_duplicate_runs_and_says_why() -> None:
    _three_recordings()
    async with await _client() as client:
        shown = (await client.get("/api/v1/recordings")).json()
        every = (await client.get("/api/v1/recordings?include_hidden=true")).json()

    assert [r["file"] for r in shown] == ["aurora-demo.json", "run_aaaaaaaaaaaa.local.json"]
    assert shown[0]["findings"] == 3 and shown[0]["case_id"] == "CASE-2026-00002"
    hidden = {r["file"]: r["hidden"] for r in every if r["hidden"]}
    assert hidden == {
        "run_bbbbbbbbbbbb.local.json": "the run failed or was cancelled before it found anything",
        "run_cccccccccccc.local.json": "another file holds the same run",
    }


async def test_a_recording_is_deleted_and_a_committed_one_is_kept() -> None:
    _three_recordings()
    async with await _client() as client:
        gone = await client.delete("/api/v1/recordings/run_aaaaaaaaaaaa.local.json")
        kept = await client.delete("/api/v1/recordings/aurora-demo.json")
        missing = await client.delete("/api/v1/recordings/run_aaaaaaaaaaaa.local.json")
        audit = (await client.get("/api/v1/audit")).json()

    assert gone.status_code == 204
    assert kept.status_code == 409 and kept.json()["error_code"] == "RECORDING_KEPT"
    assert missing.status_code == 404
    assert any(e["action"] == "recording.deleted" for e in audit)


async def test_deleting_many_needs_confirmation_and_reports_counts() -> None:
    _three_recordings()
    async with await _client() as client:
        refused = await client.delete("/api/v1/recordings?scope=all")
        hidden = (await client.delete("/api/v1/recordings?scope=hidden&confirm=delete")).json()
        left = (await client.get("/api/v1/recordings?include_hidden=true")).json()
        every = (await client.delete("/api/v1/recordings?scope=all&confirm=delete")).json()
        last = (await client.get("/api/v1/recordings?include_hidden=true")).json()

    assert refused.status_code == 400 and refused.json()["error_code"] == "CONFIRMATION_REQUIRED"
    assert hidden == {"deleted": 2, "kept": 0}
    assert {r["file"] for r in left} == {"run_aaaaaaaaaaaa.local.json", "aurora-demo.json"}
    assert every == {"deleted": 1, "kept": 1}
    assert [r["file"] for r in last] == ["aurora-demo.json"]


# --- U1c: deleting investigations and cases -------------------------------------------------------


async def test_deleting_an_investigation_removes_it_everywhere_and_says_what_is_kept() -> None:
    from app.cases.service import get_case_store
    from app.schemas.case import CaseInvestigation

    record = _finished()
    archive.write_archive(record)
    _recording(f"{record.run_id}.local.json", record.run_id, "COMPLETED", 1, "2026-10-13T05")
    cases = await get_case_store()
    await cases.save_investigation(
        CaseInvestigation(case_id=record.case_id, run_id=record.run_id, objective="x")
    )

    async with await _client() as client:
        report = (await client.delete(f"/api/v1/missions/{record.run_id}")).json()
        again = await client.delete(f"/api/v1/missions/{record.run_id}")
        audit = (await client.get("/api/v1/audit")).json()

    assert report["deleted"] == [record.run_id]
    assert report["removed"][:3] == ["the investigation", "its archive", "its recording"]
    assert "the evidence's chain of custody (append-only)" in report["kept"]
    assert again.status_code == 404
    assert get_registry().get(record.run_id) is None
    assert not archive.path_for(record.run_id).exists()
    assert await cases.case_of_run(record.run_id) is None
    assert any(e["action"] == "mission.deleted" for e in audit)
    reset_registry()
    assert get_registry().get(record.run_id) is None, "not restored after a restart either"


async def test_a_running_investigation_is_not_deleted() -> None:
    record = _finished()
    record.status = MissionStatus.RUNNING
    async with await _client() as client:
        response = await client.delete(f"/api/v1/missions/{record.run_id}")
    assert response.status_code == 409 and response.json()["error_code"] == "MISSION_RUNNING"


async def test_deleting_every_investigation_needs_confirmation_and_skips_running_ones() -> None:
    _finished("one")
    _finished("two")
    running = _finished("three")
    running.status = MissionStatus.RUNNING
    async with await _client() as client:
        refused = await client.delete("/api/v1/missions")
        report = (await client.delete("/api/v1/missions?confirm=delete")).json()
    assert refused.status_code == 400
    assert len(report["deleted"]) == 2
    assert report["skipped"] == [f"{running.run_id} (still running)"]
    assert [r.run_id for r in get_registry().records()] == [running.run_id]


async def test_deleting_a_case_takes_its_investigations_and_keeps_its_evidence() -> None:
    async with await _client() as client:
        case = (await client.post("/api/v1/cases", json={"title": "Budget overrun"})).json()
        record = _finished()
        record.case_id = case["case_id"]
        from app.cases.service import get_case_store
        from app.schemas.case import CaseEvidence, CaseInvestigation

        cases = await get_case_store()
        await cases.save_investigation(
            CaseInvestigation(case_id=case["case_id"], run_id=record.run_id, objective="x")
        )
        await cases.add_evidence(CaseEvidence(case_id=case["case_id"], evidence_id="EV-000001"))
        report = (await client.delete(f"/api/v1/cases/{case['case_id']}")).json()
        missing = await client.get(f"/api/v1/cases/{case['case_id']}")

    assert report["deleted"] == [case["case_id"], record.run_id]
    assert "the case's links to 1 evidence item(s)" in report["removed"]
    assert "the evidence items themselves, in the Evidence Locker" in report["kept"]
    assert missing.status_code == 404
    assert get_registry().get(record.run_id) is None
