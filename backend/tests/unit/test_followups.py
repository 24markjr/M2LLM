"""v4 Phase 3b: answering a clarifying question, a finding's history, run-to-run comparison, and
findings marked for re-checking when evidence arrives after them."""

from __future__ import annotations

from datetime import timedelta
from pathlib import Path

import pytest
from httpx import ASGITransport, AsyncClient

from app.api.app import create_app
from app.api.registry import MissionRecord, get_registry, reset_registry
from app.conversation import store as conversations
from app.orchestration.mission import MissionResult, MissionStatus
from app.schemas.common import new_run_id, utcnow
from app.schemas.event import EventType, ExecutionEvent
from app.schemas.finding import Finding
from app.schemas.objective import Objective
from app.schemas.verification import (
    IssueType,
    VerificationIssue,
    VerificationResult,
    VerificationStatus,
)


@pytest.fixture(autouse=True)
def _clean(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    reset_registry()
    monkeypatch.setattr(conversations, "_path", lambda case_id: tmp_path / f"{case_id}.json")


def _client() -> AsyncClient:
    return AsyncClient(transport=ASGITransport(app=create_app()), base_url="http://t")


def _verified(status: str) -> VerificationResult:
    issues = (
        [VerificationIssue(issue_type=IssueType.NO_EVIDENCE, description="no line")]
        if status != "SUPPORTED"
        else []
    )
    return VerificationResult(status=VerificationStatus(status), confidence=0.5, issues=issues)


def _run(findings: list[tuple[str, str, str]], *, case_id: str = "") -> MissionRecord:
    record = MissionRecord(
        new_run_id(), Objective(text="Check the reports."), ["aurora_project_report.txt"]
    )
    record.status = MissionStatus.COMPLETED
    record.case_id = case_id
    record.finished_at = utcnow()
    record.result = MissionResult(
        run_id=record.run_id,
        objective=record.objective,
        status=MissionStatus.COMPLETED,
        findings=[
            Finding(finding_id=fid, claim=claim, verification=_verified(status))
            for fid, claim, status in findings
        ],
    )
    get_registry()._missions[record.run_id] = record
    return record


async def test_a_clarifying_question_is_answered_by_a_new_run_with_the_answer() -> None:
    asking = _run([])
    asking.status = MissionStatus.CLARIFICATION_NEEDED
    async with _client() as client:
        response = await client.post(
            f"/api/v1/missions/{asking.run_id}/clarify", json={"answer": "The May contract."}
        )
        assert response.status_code == 202, response.text
        started = get_registry().get(response.json()["run_id"])
        assert started is not None and started.run_id != asking.run_id
        assert started.objective.text.endswith("Clarification: The May contract.")
        assert started.documents == ["aurora_project_report.txt"]

        done = _run([])
        refused = await client.post(f"/api/v1/missions/{done.run_id}/clarify", json={"answer": "x"})
        assert refused.status_code == 409


async def test_a_findings_history_gathers_every_recorded_change() -> None:
    from app.conversation.models import Recheck, Thread, Turn

    record = _run([("F-001", "Spend was 450,000", "SUPPORTED")], case_id="CASE-2026-00007")
    now = utcnow()
    record.events = [
        ExecutionEvent(
            run_id=record.run_id,
            event_type=EventType.FINDING_CREATED,
            t_offset_ms=10,
            finding_id="F-001",
            payload={"cited": 2, "cited_by_values": ["a.txt:r1"]},
            timestamp=now,
        ),
        ExecutionEvent(
            run_id=record.run_id,
            event_type=EventType.FINDING_VERIFIED,
            t_offset_ms=20,
            finding_id="F-001",
            payload={
                "status": "SUPPORTED",
                "opinions": {"baseline": "SUPPORTED", "nli": "SUPPORTED"},
            },
            timestamp=now + timedelta(seconds=1),
        ),
    ]
    conversations.save(
        Thread(
            case_id="CASE-2026-00007",
            turns=[
                Turn(
                    turn_id="T-1",
                    role="assistant",
                    text="",
                    created_at=now + timedelta(seconds=5),
                    rechecks=[
                        Recheck(
                            run_id=record.run_id,
                            finding_id="F-001",
                            claim="Spend was 450,000",
                            before="SUPPORTED",
                            after="UNSUPPORTED",
                            changed=True,
                        )
                    ],
                )
            ],
        )
    )
    async with _client() as client:
        body = (await client.get(f"/api/v1/missions/{record.run_id}/findings/F-001/history")).json()
    assert [e["kind"] for e in body["entries"]] == ["created", "verified", "rechecked"]
    assert "cited by its values" in body["entries"][0]["summary"]
    assert "nli supported" in body["entries"][1]["summary"]
    assert body["entries"][2]["summary"] == "supported -> unsupported"


async def test_two_runs_of_a_case_are_compared_finding_by_finding() -> None:
    async with _client() as client:
        case = (await client.post("/api/v1/cases", json={"title": "Aurora"})).json()["case_id"]
    first = _run(
        [
            ("F-001", "The completion dates differ: 30 April and 14 May", "SUPPORTED"),
            ("F-002", "Spend of 450,000 exceeds the budget of 380,000", "PARTIALLY_SUPPORTED"),
        ],
        case_id=case,
    )
    second = _run(
        [
            ("F-001", "Spend of 450,000 exceeds the approved budget of 380,000", "SUPPORTED"),
            ("F-002", "The vendor was paid twice", "SUPPORTED"),
        ],
        case_id=case,
    )
    async with _client() as client:
        response = await client.get(
            f"/api/v1/cases/{case}/compare", params={"a": first.run_id, "b": second.run_id}
        )
    changes = {(p["a"], p["b"], p["change"]) for p in response.json()["pairs"]}
    assert changes == {
        ("F-001", "", "only in a"),
        ("F-002", "F-001", "status changed"),
        ("", "F-002", "only in b"),
    }


async def test_evidence_added_after_a_run_marks_its_findings_for_rechecking() -> None:
    from app.cases.service import get_case_store
    from app.evidence.service import get_locker
    from app.schemas.case import CaseEvidence, CaseInvestigation
    from app.schemas.evidence_locker import EvidenceItem

    async with _client() as client:
        case = (await client.post("/api/v1/cases", json={"title": "Aurora"})).json()["case_id"]
        record = _run([("F-001", "Spend was 450,000", "SUPPORTED")], case_id=case)
        store = await get_case_store()
        await store.save_investigation(
            CaseInvestigation(case_id=case, run_id=record.run_id, objective="Check")
        )
        assert (await client.get(f"/api/v1/cases/{case}/stale")).json() == []

        locker = await get_locker()
        await locker.add(
            EvidenceItem(evidence_id="EV-000099", sha256="a" * 64, name="new_contract.pdf")
        )
        await store.add_evidence(
            CaseEvidence(
                case_id=case,
                evidence_id="EV-000099",
                added_at=record.finished_at + timedelta(minutes=5),  # type: ignore[operator]
            )
        )
        stale = (await client.get(f"/api/v1/cases/{case}/stale")).json()
    assert [(s["finding_id"], s["newer_evidence"]) for s in stale] == [
        ("F-001", ["new_contract.pdf"])
    ]


async def test_an_investigation_is_run_again_as_it_was_or_edited() -> None:
    done = _run([("F-001", "Spend was 450,000", "SUPPORTED")])
    async with _client() as client:
        same = await client.post(f"/api/v1/missions/{done.run_id}/rerun", json={})
        edited = await client.post(
            f"/api/v1/missions/{done.run_id}/rerun", json={"objective": "Only the budget, please."}
        )
        assert same.status_code == edited.status_code == 202
        again = get_registry().get(same.json()["run_id"])
        branch = get_registry().get(edited.json()["run_id"])
        assert again is not None and again.objective.text == "Check the reports."
        assert branch is not None and branch.objective.text == "Only the budget, please."
        assert again.documents == branch.documents == done.documents

        running = _run([])
        running.status = MissionStatus.RUNNING
        refused = await client.post(f"/api/v1/missions/{running.run_id}/rerun", json={})
        assert refused.status_code == 409
