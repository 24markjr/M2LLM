"""Phase 44: cases - opening them, filing investigations and evidence, counting what they hold - and
the plain-language step labels of the Professional view.

Every test gets a fresh in-memory case store and evidence locker (tests/conftest.py). The Postgres
store is tested in tests/integration/test_cases.py, inside a rolled-back transaction.
"""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest
from httpx import ASGITransport, AsyncClient

from app.api import registry as registry_module
from app.api.app import create_app
from app.api.v1.documents import wait_for_indexing
from app.cases.service import counters, file_investigation, get_case_store
from app.core.config import get_settings
from app.evidence.service import get_locker
from app.orchestration.labels import LABELS, step_label
from app.schemas.case import CaseInvestigation
from app.schemas.evidence_locker import IntegrityStatus
from app.schemas.task import TaskStatus, TaskType

REPORT = b"PROJECT HELIX - STATUS REPORT\n\nThe approved budget is 380,000.\n"


@pytest.fixture
def agent(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[Path]:
    root = tmp_path / "agent"

    def agent_dir(_self: object) -> Path:
        return root

    monkeypatch.setattr(type(get_settings()), "agent_dir", property(agent_dir))
    yield root


@pytest.fixture(autouse=True)
def _clean_registry() -> Iterator[None]:
    registry_module.reset_registry()
    yield
    registry_module.reset_registry()


async def _client() -> AsyncClient:
    return AsyncClient(transport=ASGITransport(app=create_app()), base_url="http://test")


async def _open(client: AsyncClient, title: str = "Helix budget review") -> dict[str, object]:
    response = await client.post(
        "/api/v1/cases",
        json={"title": title, "severity": "HIGH"},
        headers={"X-Jarvis-User": "lead-analyst"},
    )
    assert response.status_code == 201, response.text
    body: dict[str, object] = response.json()
    return body


def _capture_missions(monkeypatch: pytest.MonkeyPatch) -> dict[str, object]:
    """Stop at mission creation: the run itself is not under test."""
    captured: dict[str, object] = {}

    async def create(**kwargs: object) -> object:
        record = registry_module.MissionRecord(
            "run_0123456789ab",
            kwargs["objective"],  # type: ignore[arg-type]
            list(kwargs["documents"]),  # type: ignore[call-overload]
        )
        registry_module.get_registry()._missions[record.run_id] = record
        captured["record"] = record
        return record

    monkeypatch.setattr(registry_module.get_registry(), "create", create)
    return captured


# --- opening and listing --------------------------------------------------------------------------


async def test_a_case_is_numbered_by_year_and_owned_by_who_opened_it() -> None:
    async with await _client() as client:
        first = await _open(client)
        second = await _open(client, "Orion delivery shortfall")
        listing = (await client.get("/api/v1/cases")).json()
    assert str(first["case_id"]).endswith("-00001") and str(second["case_id"]).endswith("-00002")
    assert first["owner"] == "lead-analyst" and first["status"] == "OPEN"
    assert listing["store"] == "memory"
    assert [c["case"]["case_id"] for c in listing["cases"]] == [second["case_id"], first["case_id"]]


async def test_closing_records_when_and_reopening_clears_it() -> None:
    async with await _client() as client:
        case = await _open(client)
        url = f"/api/v1/cases/{case['case_id']}"
        closed = (await client.patch(url, json={"status": "CLOSED"})).json()
        reopened = (await client.patch(url, json={"status": "INVESTIGATING"})).json()
    assert closed["closed_at"] is not None and reopened["closed_at"] is None


async def test_unknown_and_malformed_cases_are_not_found() -> None:
    async with await _client() as client:
        assert (await client.get("/api/v1/cases/CASE-2026-99999")).status_code == 404
        assert (await client.get("/api/v1/cases/nope")).status_code == 404


# --- filing evidence and investigations -----------------------------------------------------------


@pytest.mark.usefixtures("agent")
async def test_an_upload_into_a_case_is_filed_there() -> None:
    async with await _client() as client:
        case = await _open(client)
        uploaded = (
            await client.post(
                f"/api/v1/documents?case={case['case_id']}",
                files=[("files", ("helix.txt", REPORT))],
            )
        ).json()[0]
        await wait_for_indexing()
        detail = (await client.get(f"/api/v1/cases/{case['case_id']}")).json()
    assert [e["item"]["evidence_id"] for e in detail["evidence"]] == [uploaded["evidence_id"]]
    assert detail["counters"]["evidence"] == 1


async def test_a_mission_in_a_case_files_itself_and_its_evidence(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured = _capture_missions(monkeypatch)
    async with await _client() as client:
        case = await _open(client)
        case_id = case["case_id"]
        response = await client.post(
            "/api/v1/missions",
            json={
                "objective": "Check the Helix budget figures.",
                "documents": ["project_report.txt"],
                "case_id": case_id,
            },
        )
        assert response.status_code == 202, response.text
        detail = (await client.get(f"/api/v1/cases/{case_id}")).json()
        listed = (await client.get("/api/v1/missions")).json()

    assert response.json()["case_id"] == case_id
    assert detail["case"]["status"] == "INVESTIGATING"  # an open case is now being investigated
    [investigation] = detail["investigations"]
    assert investigation["run_id"] == "run_0123456789ab"
    assert detail["counters"]["investigations"] == 1 and detail["counters"]["running"] == 1
    assert [e["item"]["name"] for e in detail["evidence"]] == ["project_report.txt"]
    assert listed[0]["case_id"] == case_id
    assert captured["record"].case_id == case_id  # type: ignore[attr-defined]


async def test_a_mission_cannot_be_filed_in_a_missing_or_closed_case() -> None:
    body = {"objective": "Check the Helix budget figures.", "documents": ["project_report.txt"]}
    async with await _client() as client:
        missing = await client.post("/api/v1/missions", json={**body, "case_id": "CASE-2026-99999"})
        case = await _open(client)
        await client.patch(f"/api/v1/cases/{case['case_id']}", json={"status": "CLOSED"})
        closed = await client.post("/api/v1/missions", json={**body, "case_id": case["case_id"]})
    assert missing.status_code == 404 and missing.json()["error_code"] == "CASE_NOT_FOUND"
    assert closed.status_code == 409 and closed.json()["error_code"] == "CASE_CLOSED"


@pytest.mark.usefixtures("agent")
async def test_existing_evidence_is_filed_once() -> None:
    async with await _client() as client:
        case = await _open(client)
        uploaded = (
            await client.post("/api/v1/documents", files=[("files", ("a.txt", REPORT))])
        ).json()[0]
        await wait_for_indexing()
        url = f"/api/v1/cases/{case['case_id']}/evidence"
        first = (await client.post(url, json={"evidence_ids": [uploaded["evidence_id"]]})).json()
        again = (await client.post(url, json={"evidence_ids": [uploaded["evidence_id"]]})).json()
        unknown = await client.post(url, json={"evidence_ids": ["EV-999999"]})
    assert first["added"] == 1 and again["added"] == 0
    assert unknown.status_code == 404


# --- counters -------------------------------------------------------------------------------------


@pytest.mark.usefixtures("agent")
async def test_counters_are_computed_from_what_the_case_holds() -> None:
    async with await _client() as client:
        case = await _open(client)
        case_id = str(case["case_id"])
        uploaded = (
            await client.post(
                f"/api/v1/documents?case={case_id}", files=[("files", ("a.txt", REPORT))]
            )
        ).json()[0]
        await wait_for_indexing()
    for run, (findings, verified, conflicts, gaps) in {
        "run_aaaaaaaaaaaa": (3, 2, 1, 0),
        "run_bbbbbbbbbbbb": (1, 1, 0, 2),
    }.items():
        await file_investigation(
            CaseInvestigation(
                case_id=case_id,
                run_id=run,
                objective="x",
                status="COMPLETED",
                findings=findings,
                verified=verified,
                contradictions=conflicts,
                open_gaps=gaps,
            )
        )
    locker = await get_locker()
    await locker.update(str(uploaded["evidence_id"]), integrity=IntegrityStatus.FAILED)

    store = await get_case_store()
    stored = await store.get(case_id)
    assert stored is not None
    counted = await counters(store, stored, running={"run_bbbbbbbbbbbb"})
    assert counted.model_dump() == {
        "investigations": 2,
        "running": 1,
        "evidence": 1,
        "failed_integrity": 1,
        "findings": 4,
        "verified": 3,
        "contradictions": 1,
        "open_gaps": 2,
    }


def test_a_finished_mission_records_its_outcome_for_its_case() -> None:
    from app.schemas.objective import Objective

    record = registry_module.MissionRecord(
        "run_0123456789ab", Objective(text="Check the budget figures."), []
    )
    record.case_id = "CASE-2026-00001"
    outcome = registry_module.case_investigation(record)
    assert outcome.case_id == "CASE-2026-00001" and outcome.status == "PENDING"
    assert outcome.findings == 0


# --- plain-language steps -------------------------------------------------------------------------


def test_every_task_type_has_a_plain_language_label() -> None:
    assert set(LABELS) == set(TaskType), set(TaskType) - set(LABELS)


@pytest.mark.parametrize(
    ("status", "label"),
    [
        (TaskStatus.PENDING, "Cross-check the sources against each other"),
        (TaskStatus.RUNNING, "Cross-checking the sources against each other"),
        (TaskStatus.COMPLETED, "Cross-checked the sources against each other"),
        (TaskStatus.FAILED, "Could not cross-check the sources against each other"),
        (TaskStatus.SKIPPED, "Skipped: cross-check the sources against each other"),
    ],
)
def test_a_step_reads_in_the_tense_of_its_status(status: TaskStatus, label: str) -> None:
    assert step_label(TaskType.COMPARE_SOURCES, status) == label
