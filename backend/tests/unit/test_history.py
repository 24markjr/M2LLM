"""Phase U1: investigations survive a restart; run history as records; deletion that is recorded."""

from __future__ import annotations

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
