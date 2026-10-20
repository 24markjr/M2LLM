"""Phase B3: native .evtx, docling for PDFs and pyannote speaker turns - the last two opt-in.

docling and pyannote are multi-gigabyte installs (pyannote's model is gated behind a Hugging Face
token), so they are exercised here through stand-in modules: what is tested is that JARVIS uses them
when they are there and is unchanged when they are not.
"""

from __future__ import annotations

import sys
import types
from pathlib import Path

import pytest

from app.core.config import get_settings
from app.tools import formats, media

EVENT = (
    '<?xml version="1.0" encoding="utf-8"?>'
    '<Event xmlns="http://schemas.microsoft.com/win/2004/08/events/event"><System>'
    "<EventID>4624</EventID><Computer>SRV-DB</Computer>"
    '<TimeCreated SystemTime="2026-03-03T09:14:02Z"/></System>'
    '<EventData><Data Name="TargetUserName">svc_admin</Data>'
    '<Data Name="IpAddress">10.0.0.12</Data></EventData></Event>'
)


class _Record:
    def xml(self) -> str:
        return EVENT


class _Evtx:
    def __init__(self, path: str) -> None:
        self.path = path

    def __enter__(self) -> _Evtx:
        return self

    def __exit__(self, *_: object) -> None:
        return None

    def records(self) -> list[_Record]:
        return [_Record(), _Record()]


def test_a_native_evtx_is_read_as_events(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    module = types.ModuleType("Evtx.Evtx")
    module.Evtx = _Evtx  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "Evtx", types.ModuleType("Evtx"))
    monkeypatch.setitem(sys.modules, "Evtx.Evtx", module)
    path = tmp_path / "security.evtx"
    path.write_bytes(b"ElfFile\x00")
    document = formats.parse(path)
    lines = document.text.splitlines()
    assert document.kind == "event_log" and len(lines) == 2
    assert "SRV-DB" in lines[0] and "svc_admin" in lines[0] and "10.0.0.12" in lines[0]


def test_docling_reads_a_pdf_only_when_chosen(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    class _Doc:
        def export_to_markdown(self) -> str:
            return "# Budget\n| Item | Amount |\n| Migration | 450,000 |"

    class _Converter:
        def convert(self, _path: str) -> types.SimpleNamespace:
            return types.SimpleNamespace(document=_Doc())

    module = types.ModuleType("docling.document_converter")
    module.DocumentConverter = _Converter  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "docling", types.ModuleType("docling"))
    monkeypatch.setitem(sys.modules, "docling.document_converter", module)
    path = tmp_path / "budget.pdf"
    path.write_bytes(b"%PDF-1.4")
    assert formats.load_pdf_with_docling(path) is None  # default reader: pypdf
    monkeypatch.setattr(get_settings(), "pdf_reader", "docling")
    laid_out = formats.load_pdf_with_docling(path)
    assert laid_out is not None and "| Migration | 450,000 |" in laid_out.text


def test_speaker_turns_label_the_transcript_and_are_off_by_default() -> None:
    turns = [(0.0, 4.0, "SPEAKER_00"), (4.5, 9.0, "SPEAKER_01")]
    assert media.speaker_at(turns, 2.0) == "SPEAKER_00"
    assert media.speaker_at(turns, 6.0) == "SPEAKER_01"
    assert media.speaker_at(turns, 4.2) == ""
    assert media.speaker_turns(Path("call.wav")) == []  # DIARIZE off: no labels, no model loaded
