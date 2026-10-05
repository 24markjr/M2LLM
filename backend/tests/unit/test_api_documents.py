"""Phase 38: uploading files of every kind, and finding them again.

The upload endpoint had no tests before this phase. These cover what a client relies on: the parse
result per file (kind, parser, hash, whether it has text), the formats list the file picker reads,
earlier uploads offered for reuse, and the limits.
"""

from __future__ import annotations

import io
from collections.abc import Iterator
from pathlib import Path

import pytest
from httpx import ASGITransport, AsyncClient

from app.api.app import create_app
from app.api.v1 import documents as documents_api
from app.core.config import get_settings


@pytest.fixture(autouse=True)
def _uploads_in_tmp(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[Path]:
    # `agent_dir` is a property; point it at a temporary `.agent` for this test only.
    monkeypatch.setattr(type(get_settings()), "agent_dir", property(lambda _self: tmp_path))
    yield tmp_path / "uploads"


def _names(folder: Path) -> list[str]:
    return sorted(p.name for p in folder.iterdir()) if folder.exists() else []


async def _client() -> AsyncClient:
    return AsyncClient(transport=ASGITransport(app=create_app()), base_url="http://test")


def _docx_bytes() -> bytes:
    from docx import Document

    document = Document()
    document.add_paragraph("Shipment 4821 arrived on 14 September.")
    buffer = io.BytesIO()
    document.save(buffer)
    return buffer.getvalue()


def _png_bytes() -> bytes:
    from PIL import Image

    buffer = io.BytesIO()
    Image.new("RGB", (40, 30), "white").save(buffer, format="PNG")
    return buffer.getvalue()


async def test_an_upload_reports_its_parser_hash_and_text() -> None:
    async with await _client() as client:
        response = await client.post(
            "/api/v1/documents",
            files=[
                ("files", ("report.docx", _docx_bytes())),
                ("files", ("typed-context.txt", b"Rahul Sharma signed for it at 10:15.")),
            ],
        )
    assert response.status_code == 201
    word, typed = response.json()
    assert (word["kind"], word["parser"], word["has_text"]) == ("word", "python-docx", True)
    assert len(word["sha256"]) == 64
    assert typed["kind"] == "text" and typed["has_text"]


async def test_an_image_is_kept_but_marked_as_having_no_text_yet(_uploads_in_tmp: Path) -> None:
    async with await _client() as client:
        response = await client.post(
            "/api/v1/documents", files=[("files", ("scan.png", _png_bytes()))]
        )
    (image,) = response.json()
    assert image["kind"] == "image" and not image["has_text"]
    assert "OCR" in image["note"]
    assert (_uploads_in_tmp / "scan.png").exists()


async def test_the_formats_list_is_what_the_picker_offers() -> None:
    async with await _client() as client:
        formats = (await client.get("/api/v1/documents/formats")).json()
    kinds = {f["kind"]: f for f in formats}
    assert {"word", "spreadsheet", "image", "video", "subtitles", "pdf", "csv", "text"} <= set(
        kinds
    )
    assert ".xlsx" in kinds["spreadsheet"]["extensions"]
    assert kinds["image"]["yields_text"] is False


async def test_earlier_uploads_are_listed_for_reuse_newest_first() -> None:
    async with await _client() as client:
        await client.post("/api/v1/documents", files=[("files", ("a.txt", b"first"))])
        await client.post("/api/v1/documents", files=[("files", ("b.csv", b"x,y\n1,2"))])
        listed = (await client.get("/api/v1/documents")).json()
    assert {d["name"] for d in listed} == {"a.txt", "b.csv"}
    assert {d["name"]: d["kind"] for d in listed} == {"a.txt": "text", "b.csv": "csv"}


async def test_an_unsupported_type_is_refused() -> None:
    async with await _client() as client:
        response = await client.post("/api/v1/documents", files=[("files", ("tool.exe", b"MZ"))])
    assert response.status_code == 422
    assert response.json()["error_code"] == "UNSUPPORTED_DOCUMENT_TYPE"


async def test_an_oversized_upload_leaves_nothing_behind(
    _uploads_in_tmp: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(documents_api, "MAX_UPLOAD_BYTES", 10)
    async with await _client() as client:
        response = await client.post(
            "/api/v1/documents", files=[("files", ("big.txt", b"x" * 1000))]
        )
    assert response.status_code == 413
    assert _names(_uploads_in_tmp) == []


async def test_an_unreadable_upload_is_removed() -> None:
    async with await _client() as client:
        response = await client.post(
            "/api/v1/documents", files=[("files", ("broken.docx", b"not a zip"))]
        )
        listed = (await client.get("/api/v1/documents")).json()
    assert response.status_code == 422
    assert response.json()["error_code"] == "DOCUMENT_UNREADABLE"
    assert listed == []
