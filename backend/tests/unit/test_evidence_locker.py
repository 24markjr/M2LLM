"""Phase 43: the Evidence Locker - content-addressed storage, chain of custody, integrity.

Every test runs against a fresh in-memory locker and a temporary evidence folder
(tests/conftest.py). The Postgres locker, and the trigger that makes custody append-only, are
tested in tests/integration/test_evidence_locker.py.
"""

from __future__ import annotations

import ast
from collections.abc import Iterator
from pathlib import Path

import pytest
from httpx import ASGITransport, AsyncClient

from app.api.app import create_app
from app.api.v1.documents import wait_for_indexing
from app.core.config import get_settings
from app.evidence import service, store
from app.evidence.service import record_citations
from app.schemas.evidence_locker import CustodyAction, IntegrityStatus

REPORT = b"PROJECT HELIX - STATUS REPORT\n\nThe approved budget is 380,000.\n"


@pytest.fixture
def agent(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[Path]:
    """`.agent` in a temporary folder, so uploads land there too."""
    root = tmp_path / "agent"

    def agent_dir(_self: object) -> Path:
        return root

    monkeypatch.setattr(type(get_settings()), "agent_dir", property(agent_dir))
    yield root


async def _client() -> AsyncClient:
    return AsyncClient(transport=ASGITransport(app=create_app()), base_url="http://test")


async def _upload(client: AsyncClient, name: str, data: bytes) -> dict[str, object]:
    response = await client.post(
        "/api/v1/documents",
        files=[("files", (name, data))],
        headers={"X-Jarvis-User": "analyst-7"},
    )
    assert response.status_code == 201, response.text
    body: dict[str, object] = response.json()[0]
    return body


def _actions(detail: dict[str, object]) -> list[str]:
    return [e["action"] for e in detail["custody"]]  # type: ignore[index, union-attr]


# --- the store -----------------------------------------------------------------------------------


def test_the_store_is_content_addressed_and_write_once(tmp_path: Path) -> None:
    source = tmp_path / "a.txt"
    source.write_bytes(REPORT)
    sha, kept = store.put(source)
    assert kept == store.path_for(sha) and kept.read_bytes() == REPORT
    # The same bytes again: nothing written, the same place.
    again = tmp_path / "copy-with-another-name.txt"
    again.write_bytes(REPORT)
    assert store.put(again) == (sha, kept)
    assert store.rehash(sha) == sha
    assert store.rehash("0" * 64) is None


# --- intake and custody through the upload API ----------------------------------------------------


@pytest.mark.usefixtures("agent")
async def test_an_upload_becomes_an_evidence_item_with_its_custody() -> None:
    async with await _client() as client:
        uploaded = await _upload(client, "helix.txt", REPORT)
        await wait_for_indexing()
        evidence_id = uploaded["evidence_id"]
        assert str(evidence_id).startswith("EV-") and uploaded["custody"] == "memory"
        detail = (await client.get(f"/api/v1/evidence/{evidence_id}")).json()

    item = detail["item"]
    assert item["sha256"] == uploaded["sha256"] and item["collected_by"] == "analyst-7"
    assert item["parser"] and item["integrity"] == "VERIFIED"
    assert _actions(detail) == ["ACQUIRED", "HASHED", "STORED", "PARSED", "INDEXED"]
    assert detail["locker"] == "memory"


@pytest.mark.usefixtures("agent")
async def test_the_same_bytes_are_one_item_acquired_twice() -> None:
    async with await _client() as client:
        first = await _upload(client, "a.txt", REPORT)
        second = await _upload(client, "a.txt", REPORT)
        await wait_for_indexing()
        detail = (await client.get(f"/api/v1/evidence/{first['evidence_id']}")).json()
    assert first["evidence_id"] == second["evidence_id"]
    assert _actions(detail).count("ACQUIRED") == 2


@pytest.mark.usefixtures("agent")
async def test_a_changed_file_under_the_same_name_is_a_new_version() -> None:
    async with await _client() as client:
        first = await _upload(client, "a.txt", REPORT)
        second = await _upload(client, "a.txt", REPORT + b"Spend to date is 450,000.\n")
        await wait_for_indexing()
        current = (await client.get("/api/v1/evidence/by-name/a.txt")).json()
        detail = (await client.get(f"/api/v1/evidence/{second['evidence_id']}")).json()
    assert first["evidence_id"] != second["evidence_id"]
    assert current["evidence_id"] == second["evidence_id"]
    assert [v["evidence_id"] for v in detail["versions"]] == [first["evidence_id"]]


@pytest.mark.usefixtures("agent")
async def test_an_unreadable_upload_stays_in_custody_as_parse_failed() -> None:
    async with await _client() as client:
        response = await client.post(
            "/api/v1/documents", files=[("files", ("broken.docx", b"not a zip"))]
        )
        assert response.status_code == 422
        listing = (await client.get("/api/v1/evidence")).json()
    [summary] = listing["items"]
    async with await _client() as client:
        detail = (await client.get(f"/api/v1/evidence/{summary['item']['evidence_id']}")).json()
    assert _actions(detail)[-1] == "PARSE_FAILED"


# --- integrity ------------------------------------------------------------------------------------


@pytest.mark.usefixtures("agent")
async def test_a_tampered_working_copy_is_left_out_of_a_mission(agent: Path) -> None:
    async with await _client() as client:
        uploaded = await _upload(client, "helix.txt", REPORT)
        await wait_for_indexing()
        (agent / "uploads" / "helix.txt").write_bytes(REPORT.replace(b"380,000", b"980,000"))
        response = await client.post(
            "/api/v1/missions",
            json={"objective": "Check the Helix budget figures.", "documents": ["helix.txt"]},
        )
        detail = (await client.get(f"/api/v1/evidence/{uploaded['evidence_id']}")).json()

    assert response.status_code == 422
    body = response.json()
    assert body["error_code"] == "NO_READABLE_DOCUMENTS" and "integrity" in body["message"]
    assert detail["item"]["integrity"] == "FAILED"
    assert _actions(detail)[-1] == "INTEGRITY_FAILED"


@pytest.mark.usefixtures("agent")
async def test_a_tampered_original_fails_verification_and_a_restored_one_passes() -> None:
    async with await _client() as client:
        uploaded = await _upload(client, "helix.txt", REPORT)
        await wait_for_indexing()
        kept = store.path_for(str(uploaded["sha256"]))
        kept.chmod(0o644)
        kept.write_bytes(b"something else")
        failed = (await client.post(f"/api/v1/evidence/{uploaded['evidence_id']}/verify")).json()
        kept.write_bytes(REPORT)
        restored = (await client.post(f"/api/v1/evidence/{uploaded['evidence_id']}/verify")).json()
        detail = (await client.get(f"/api/v1/evidence/{uploaded['evidence_id']}")).json()
    assert failed["integrity"] == "FAILED" and "stored original changed" in failed["reason"]
    assert restored["integrity"] == "VERIFIED"
    assert _actions(detail)[-2:] == ["INTEGRITY_FAILED", "VERIFIED"]
    assert detail["item"]["integrity"] == "VERIFIED"


# --- missions: analysed and cited -----------------------------------------------------------------


@pytest.mark.usefixtures("agent")
async def test_a_mission_records_what_it_analysed_and_findings_what_they_cited(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.api import registry as registry_module

    registry_module.reset_registry()
    created = {}

    async def create(**kwargs: object) -> object:
        record = registry_module.MissionRecord("run_0123456789ab", kwargs["objective"], [])  # type: ignore[arg-type]
        created["record"] = record
        return record

    monkeypatch.setattr(registry_module.get_registry(), "create", create)
    async with await _client() as client:
        uploaded = await _upload(client, "helix.txt", REPORT)
        await wait_for_indexing()
        response = await client.post(
            "/api/v1/missions",
            json={"objective": "Check the Helix budget figures.", "documents": ["helix.txt"]},
        )
        assert response.status_code == 202, response.text
        assert response.json()["evidence"] == {"helix.txt": uploaded["evidence_id"]}

        evidence = {"helix.txt": str(uploaded["evidence_id"])}
        cited = await record_citations(
            "run_0123456789ab",
            evidence,
            [("F-001", "The approved budget is 380,000", "helix.txt", "helix.txt:r3")],
        )
        detail = (await client.get(f"/api/v1/evidence/{uploaded['evidence_id']}")).json()
        findings = (await client.get(f"/api/v1/evidence/{uploaded['evidence_id']}/findings")).json()
    registry_module.reset_registry()

    assert cited == 1
    assert _actions(detail)[-2:] == ["ANALYSED", "CITED"]
    assert findings == [
        {
            "run_id": "run_0123456789ab",
            "finding_id": "F-001",
            "locator": "helix.txt:r3",
            "claim": "The approved budget is 380,000",
            "at": findings[0]["at"],
        }
    ]


async def test_a_fixture_a_mission_reads_is_imported_with_its_unknown_history() -> None:
    from app.tools.loader import resolve_document

    path = resolve_document("aurora_project_report.txt")
    admitted, excluded = await service.admit_for_mission({"aurora_project_report.txt": path})
    assert not excluded
    locker = await service.get_locker()
    [event] = await locker.history(admitted["aurora_project_report.txt"])
    assert event.action is CustodyAction.IMPORTED
    item = await locker.get(admitted["aurora_project_report.txt"])
    assert item is not None and item.source == "repository fixture"
    assert item.integrity is IntegrityStatus.VERIFIED


# --- listing, import, metadata, download ----------------------------------------------------------


async def test_uploads_that_predate_the_locker_are_imported_once(agent: Path) -> None:
    (agent / "uploads").mkdir(parents=True)
    (agent / "uploads" / "old.txt").write_bytes(REPORT)
    async with await _client() as client:
        first = (await client.get("/api/v1/evidence")).json()
        second = (await client.get("/api/v1/evidence")).json()
    assert first["imported"] == 1 and second["imported"] == 0
    assert first["items"][0]["item"]["source"] == "found in the uploads folder"


@pytest.mark.usefixtures("agent")
async def test_a_metadata_change_is_recorded_from_and_to() -> None:
    async with await _client() as client:
        uploaded = await _upload(client, "helix.txt", REPORT)
        await wait_for_indexing()
        url = f"/api/v1/evidence/{uploaded['evidence_id']}"
        changed = await client.patch(
            url, json={"classification": "CONFIDENTIAL"}, headers={"X-Jarvis-User": "lead"}
        )
        unchanged = await client.patch(url, json={"classification": "CONFIDENTIAL"})
        detail = (await client.get(url)).json()
    assert changed.json()["classification"] == "CONFIDENTIAL"
    assert unchanged.status_code == 200
    [event] = [e for e in detail["custody"] if e["action"] == "METADATA_CHANGED"]
    assert event["actor"] == "lead"
    assert event["details"]["classification"] == {"from": "UNCLASSIFIED", "to": "CONFIDENTIAL"}


@pytest.mark.usefixtures("agent")
async def test_the_original_downloads_byte_for_byte() -> None:
    async with await _client() as client:
        uploaded = await _upload(client, "helix.txt", REPORT)
        await wait_for_indexing()
        response = await client.get(f"/api/v1/evidence/{uploaded['evidence_id']}/download")
        missing = await client.get("/api/v1/evidence/EV-999999")
        malformed = await client.get("/api/v1/evidence/not-an-id")
    assert response.status_code == 200 and response.content == REPORT
    assert missing.status_code == 404 and malformed.status_code == 404


# --- invariant ------------------------------------------------------------------------------------


def test_only_the_store_writes_to_the_evidence_folder() -> None:
    """Every module that can locate stored evidence is listed, and none but the store writes."""
    app_dir = Path(__file__).parents[2] / "app"
    locating = {
        str(path.relative_to(app_dir)).replace("\\", "/")
        for path in app_dir.rglob("*.py")
        if any(
            name in path.read_text("utf-8")
            for name in ("evidence_root(", "store.path_for(", "path_for(item")
        )
    }
    # cyber/recall.py (Phase 52) reads other cases' stored originals to compare indicators.
    allowed = {"evidence/store.py", "evidence/service.py", "api/v1/evidence.py", "cyber/recall.py"}
    assert locating <= allowed, locating
    writes = {"write_bytes", "write_text", "copyfile", "copy2", "unlink", "rename", "replace"}
    for module in locating - {"evidence/store.py"}:
        tree = ast.parse((app_dir / module).read_text("utf-8"))
        called = {
            node.func.attr
            for node in ast.walk(tree)
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
        }
        assert not (called & writes - {"replace"}) or module == "evidence/store.py", module
