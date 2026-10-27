"""v4 Phase 10: domain packs, watch folders and scheduled re-investigation."""

from __future__ import annotations

from datetime import timedelta
from pathlib import Path
from typing import Any

import pytest
from httpx import ASGITransport, AsyncClient

from app.api.app import create_app
from app.api.registry import reset_registry
from app.ops import governance, watch
from app.packs import all_packs, get_pack
from app.schemas.common import utcnow
from app.schemas.investigation_report import Severity


@pytest.fixture(autouse=True)
def _clean(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    reset_registry()
    monkeypatch.setattr(governance, "_policy_path", lambda: tmp_path / "policy.json")


def _client() -> AsyncClient:
    return AsyncClient(transport=ASGITransport(app=create_app()), base_url="http://t")


# --- domain packs --------------------------------------------------------------------------------


def test_the_packs_ship_and_general_changes_nothing() -> None:
    ids = {p.id for p in all_packs()}
    assert {
        "general",
        "financial-audit",
        "procurement",
        "cyber-incident",
        "project-assurance",
    } <= ids
    general = get_pack("general")
    assert general.severity == {} and general.attributes == []
    assert general.report.title == "Investigation Report"
    assert get_pack("no-such-pack").id == "general"


def test_a_pack_raises_severity_with_its_reason() -> None:
    audit = get_pack("financial-audit")
    level, reason = audit.severity_for("Invoice INV-1042 was paid twice to Blue Harbor") or (
        None,
        "",
    )
    assert level is Severity.HIGH and "Financial audit" in reason and "paid twice" in reason
    assert audit.severity_for("The go-live date is 12 June 2026") is None
    cyber = get_pack("cyber-incident")
    assert cyber.severity_for("lsass memory was read by procdump")[0] is Severity.CRITICAL  # type: ignore[index]


def test_a_pack_words_the_report_and_never_lowers_a_severity() -> None:
    from app.reporting.builder import build_report
    from app.reporting.document import build_document
    from tests.unit.test_investigation_report import _result

    pack = get_pack("financial-audit")
    plain = build_report(_result())
    packed = build_report(_result(), pack=pack)
    for a, b in zip(
        [*plain.established, *plain.not_established],
        [*packed.established, *packed.not_established],
        strict=True,
    ):
        from app.schemas.investigation_report import SEVERITY_ORDER

        assert SEVERITY_ORDER.index(b.severity) >= SEVERITY_ORDER.index(a.severity)
    raised = [
        f
        for f in packed.not_established + packed.established
        if "Financial audit" in f.severity_reason
    ]
    assert raised, "the fixture's 'paid twice' finding is raised by the pack"
    document = build_document(packed, pack.report)
    assert document.title == "Financial Audit Report"
    assert [b.text for b in document.blocks if b.kind == "heading"][:2] == [
        "Audit summary",
        "Audit findings",
    ]


async def test_the_organisation_chooses_its_pack() -> None:
    async with _client() as client:
        assert (await client.get("/api/v1/packs")).json()["current"] == "general"
        bad = await client.put("/api/v1/governance/policy", json={"pack": "astrology"})
        assert bad.status_code == 422
        ok = await client.put("/api/v1/governance/policy", json={"pack": "procurement"})
        assert ok.status_code == 200
        body = (await client.get("/api/v1/packs")).json()
    assert body["current"] == "procurement"
    starters = next(p for p in body["packs"] if p["id"] == "procurement")["starter_questions"]
    assert starters


# --- watch folders and scheduled re-investigation ----------------------------------------------


async def test_a_watched_folder_takes_new_files_in_as_evidence_once(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    from app.core.config import get_settings

    monkeypatch.setattr(type(get_settings()), "agent_dir", property(lambda _self: tmp_path))
    reruns: list[list[str]] = []

    async def fake_rerun(case_id: str, new_files: list[str]) -> str:
        reruns.append(new_files)
        return "run_00000000000a"

    monkeypatch.setattr(watch, "_rerun_latest", fake_rerun)
    async with _client() as client:
        case = (await client.post("/api/v1/cases", json={"title": "Watched"})).json()["case_id"]
        off = (await client.post(f"/api/v1/cases/{case}/watch/scan")).json()
        assert off["reason"] == "watching is off for this case"
        view = (await client.put(f"/api/v1/cases/{case}/watch", json={"enabled": True})).json()
        folder = Path(view["folder"])
        (folder / "new_contract.txt").write_text("Contract value: 4,80,000\n", encoding="utf-8")

        first = (await client.post(f"/api/v1/cases/{case}/watch/scan")).json()
        assert first["taken"] == ["new_contract.txt"] and first["rerun"] == "run_00000000000a"
        again = (await client.post(f"/api/v1/cases/{case}/watch/scan")).json()
        assert again["taken"] == [] and again["rerun"] == ""  # taken once

        detail = (await client.get(f"/api/v1/cases/{case}")).json()
        names = [e["item"]["name"] for e in detail["evidence"]]
        assert names == ["new_contract.txt"]
        custody = (
            await client.get(f"/api/v1/evidence/{detail['evidence'][0]['item']['evidence_id']}")
        ).json()
        assert "watch folder" in custody["item"]["source"]

        (folder / "new_contract.txt").write_text("Contract value: 5,10,000\n", encoding="utf-8")
        changed = (await client.post(f"/api/v1/cases/{case}/watch/scan")).json()
        assert changed["taken"] == ["new_contract.txt"]  # a new version is taken again
    assert reruns == [["new_contract.txt"], ["new_contract.txt"]]


async def test_a_case_is_re_investigated_on_its_schedule(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    from app.core.config import get_settings

    monkeypatch.setattr(type(get_settings()), "agent_dir", property(lambda _self: tmp_path))
    calls: list[Any] = []

    async def fake_rerun(case_id: str, new_files: list[str]) -> str:
        calls.append(new_files)
        return "run_00000000000b"

    monkeypatch.setattr(watch, "_rerun_latest", fake_rerun)
    case = "CASE-2026-00042"
    watch.save(case, watch.WatchSettings(enabled=True, rerun_every_days=7))
    first = await watch.scan(case)
    assert first.rerun and first.reason == "every 7 day(s)"
    assert (await watch.scan(case)).rerun == ""  # not due again yet
    stale = watch.load(case).model_copy(update={"last_rerun_at": utcnow() - timedelta(days=8)})
    watch.save(case, stale)
    assert (await watch.scan(case)).rerun == "run_00000000000b"
    assert calls == [[], []]
