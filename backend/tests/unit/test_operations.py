"""v4 Phase 8: the queue, metrics and cost, and data governance."""

from __future__ import annotations

import asyncio
from datetime import timedelta
from pathlib import Path
from typing import Any

import pytest
from httpx import ASGITransport, AsyncClient

from app.api.app import create_app
from app.api.registry import MissionRecord, get_registry, reset_registry
from app.core.config import get_settings
from app.ops import governance
from app.ops.metrics import run_metrics, summarise
from app.orchestration.mission import MissionResult, MissionStatus
from app.schemas.common import new_run_id, utcnow
from app.schemas.event import EventType, ExecutionEvent
from app.schemas.finding import Finding
from app.schemas.objective import Objective


@pytest.fixture(autouse=True)
def _clean(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    reset_registry()
    monkeypatch.setattr(governance, "_policy_path", lambda: tmp_path / "policy.json")


def _client() -> AsyncClient:
    return AsyncClient(transport=ASGITransport(app=create_app()), base_url="http://t")


def _finished(
    text: str = "Check the reports.", days_old: int = 0, claim: str = ""
) -> MissionRecord:
    record = MissionRecord(new_run_id(), Objective(text=text), ["memo.txt"])
    record.created_at = utcnow() - timedelta(days=days_old)
    record.started_at = record.created_at + timedelta(seconds=3)
    record.finished_at = record.started_at + timedelta(seconds=60)
    record.status = MissionStatus.COMPLETED
    record.texts = {"memo.txt": "Paid to Ravi Kumar, ravi.kumar@example.in, 9876543210.\n"}
    record.result = MissionResult(
        run_id=record.run_id,
        objective=record.objective,
        status=MissionStatus.COMPLETED,
        findings=[Finding(finding_id="F-001", claim=claim or "Spend was 450,000")],
    )
    get_registry()._missions[record.run_id] = record
    return record


# --- the queue -----------------------------------------------------------------------------------


async def test_ten_investigations_at_once_queue_and_all_finish(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The Phase 8 bar: ten at once run cleanly - never more than the slots, every one finished."""
    monkeypatch.setattr(get_settings(), "max_concurrent_runs", 2)
    reset_registry()
    registry = get_registry()
    peak = 0
    original = registry._run

    async def watched(*args: Any, **kwargs: Any) -> None:
        nonlocal peak
        peak = max(peak, registry.running + 1)
        await asyncio.sleep(0.05)  # long enough for the others to pile up behind the slots
        await original(*args, **kwargs)

    monkeypatch.setattr(registry, "_run", watched)
    from app.api.v1 import missions
    from app.llm.echo import EchoProvider

    model = EchoProvider(synthesize=True)  # answers every role; the pipeline itself is real
    monkeypatch.setattr(missions, "get_provider", lambda: model)
    body = {
        "objective": "Investigate the Aurora reports.",
        "documents": ["aurora_project_report.txt"],
    }
    async with _client() as client:
        started = await asyncio.gather(
            *(client.post("/api/v1/missions", json=body) for _ in range(10))
        )
        assert {r.status_code for r in started} == {202}
        positions = [r.json()["queue_position"] for r in started]
        assert max(positions) >= 1, "some waited for a slot"
        ids = [r.json()["run_id"] for r in started]
        for _ in range(400):
            if all(get_registry().get(i).is_finished() for i in ids):  # type: ignore[union-attr]
                break
            await asyncio.sleep(0.05)
    records = [get_registry().get(i) for i in ids]
    # Every one ran to an end - none left waiting or running. The stand-in model plans nothing, so
    # each ends at its planning check; the live load test runs the real model (see the changelog).
    assert all(r is not None and r.is_finished() for r in records)
    assert {r.result.error_message for r in records if r and r.result} == {"the plan has no tasks"}
    assert peak <= 2
    assert registry.waiting == 0 and registry.running == 0


async def test_a_full_queue_is_refused(monkeypatch: pytest.MonkeyPatch) -> None:
    from app.api import registry as registry_module

    monkeypatch.setattr(registry_module, "MAX_QUEUE", 0)
    async with _client() as client:
        response = await client.post(
            "/api/v1/missions", json={"objective": "Investigate the reports.", "documents": []}
        )
    assert response.status_code == 429 and "queue" in response.json()["message"]


# --- metrics and cost ----------------------------------------------------------------------------


def test_metrics_and_cost_come_from_the_runs_own_timeline() -> None:
    record = _finished()
    record.events = [
        ExecutionEvent(
            run_id=record.run_id,
            event_type=EventType.LLM_CALL_COMPLETED,
            t_offset_ms=i,
            payload={
                "ok": i != 2,
                "latency_ms": 9000,
                "prompt_tokens": 1000,
                "completion_tokens": 200,
                "repair_attempt": 1 if i == 1 else 0,
            },
        )
        for i in range(4)
    ]
    m = run_metrics(record)
    assert (m.llm_calls, m.failed_calls, m.repairs) == (4, 1, 1)
    assert (m.prompt_tokens, m.completion_tokens, m.model_seconds) == (4000, 800, 36.0)
    assert m.queue_wait_s == 3.0 and m.duration_s == 60.0
    settings = get_settings()
    expected = 36 / 3600 * settings.gpu_cost_per_hour_inr + 60 / 3600 * (
        settings.server_cost_per_hour_inr / settings.max_concurrent_runs
    )
    assert m.cost_inr == round(expected, 4)

    summary = summarise([record, _finished(days_old=30)], days=7)
    assert summary.investigations == 1 and summary.completed == 1
    assert summary.cost_per_investigation_inr == round(m.cost_inr, 2)


async def test_the_dashboard_answers_for_the_organisation() -> None:
    _finished()
    async with _client() as client:
        body = (await client.get("/api/v1/ops/metrics", params={"days": 7})).json()
        runs = (await client.get("/api/v1/ops/metrics/runs")).json()
    assert body["investigations"] == 1 and body["rates"]["gpu_per_hour_inr"] > 0
    assert len(runs) == 1 and runs[0]["duration_s"] == 60.0


# --- governance ----------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("text", "masked"),
    [
        ("mail ravi.kumar@example.in now", "mail [email] now"),
        ("call +91 98765 43210 or 9876543210", "call [phone] or [phone]"),
        ("Aadhaar 2345 6789 0123", "Aadhaar [aadhaar]"),
        ("PAN ABCDE1234F", "PAN [pan]"),
        ("card 4111 1111 1111 1111", "card [card]"),
        ("spend of 4,80,000 on 12 March 2026", "spend of 4,80,000 on 12 March 2026"),
    ],
)
def test_personal_details_are_masked_and_figures_are_not(text: str, masked: str) -> None:
    assert governance.mask(text) == masked


async def test_retention_deletes_only_what_is_older_than_the_policy() -> None:
    old, new = _finished(days_old=40), _finished(days_old=2)
    async with _client() as client:
        await client.put("/api/v1/governance/policy", json={"retention_days": 30})
        dry = (await client.post("/api/v1/governance/retention")).json()
        assert dry["dry_run"] and dry["deleted"] == [old.run_id]
        assert get_registry().get(old.run_id) is not None  # a dry run deletes nothing
        done = (await client.post("/api/v1/governance/retention", params={"dry_run": False})).json()
    assert done["deleted"] == [old.run_id]
    assert get_registry().get(old.run_id) is None and get_registry().get(new.run_id) is not None


async def test_a_data_subject_request_finds_then_erases() -> None:
    held = _finished(claim="Ravi Kumar approved the payment")
    other = _finished()
    other.texts = {"memo.txt": "Nothing personal here.\n"}
    async with _client() as client:
        found = (
            await client.post(
                "/api/v1/governance/subject/search", json={"identifier": "Ravi Kumar"}
            )
        ).json()
        assert found["investigations"] == [held.run_id]
        assert {h["where"] for h in found["hits"]} == {"document", "finding"}
        assert found["evidence_files"] == ["memo.txt"]
        refused = await client.post(
            "/api/v1/governance/subject/erase", json={"identifier": "Ravi Kumar"}
        )
        assert refused.status_code == 400
        erased = (
            await client.post(
                "/api/v1/governance/subject/erase",
                json={"identifier": "Ravi Kumar", "confirm": "erase"},
            )
        ).json()
        assert erased["erased"] and get_registry().get(held.run_id) is None
        assert get_registry().get(other.run_id) is not None
        audit_csv = await client.get("/api/v1/governance/audit.csv")
    assert audit_csv.headers["content-type"].startswith("text/csv")
    assert "governance.subject_erased" in audit_csv.text


def test_operations_are_for_admins_only() -> None:
    from app.auth.models import Role
    from app.auth.permissions import allowed

    for path in (
        "/api/v1/ops/metrics",
        "/api/v1/governance/policy",
        "/api/v1/governance/audit.csv",
    ):
        assert allowed(Role.ADMIN, "GET", path)
        assert not allowed(Role.ANALYST, "GET", path)
        assert not allowed(Role.VIEWER, "GET", path)
