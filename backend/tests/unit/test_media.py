"""Phase 39: reading, seeing and hearing what images, scans, video and audio contain.

OCR runs for real (it is local and fast). The vision model is the echo provider answering as one,
so the tests check what is done with a description, not the model's eyesight. Speech recognition
is replaced by a stub: Whisper downloads a model on first use, and what is under test is what
happens to its segments. Every file is generated in the test.
"""

from __future__ import annotations

import json
from collections.abc import Iterator
from pathlib import Path

import pytest

from app.core.config import get_settings
from app.integrations.verification import described_only
from app.intelligence.knowledge.extraction import Chunk, ground
from app.llm.echo import EchoProvider
from app.schemas.common import SourceLocator
from app.schemas.evidence import SEEN_MARKER, EvidenceRef, ResolutionStatus, is_seen_line
from app.schemas.finding import Finding
from app.schemas.verification import IssueType, VerificationResult, VerificationStatus
from app.tools import media
from app.tools.formats import parse, prepare

VISION = json.dumps(
    {
        "kind": "photo",
        "summary": "A wooden crate on a loading dock, its lid split.",
        "observations": ["The crate is stencilled 4821", "A forklift stands beside it"],
        "uncertain": ["a label on the side is too small to read"],
    }
)


@pytest.fixture(autouse=True)
def _agent_in_tmp(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[Path]:
    """The media cache under a temporary `.agent`, so tests never touch the real one."""
    monkeypatch.setattr(media, "cache_dir", lambda: tmp_path / "media-cache")
    monkeypatch.setattr(get_settings(), "media_understanding", True)
    yield tmp_path


def _picture(text: str, size: tuple[int, int] = (720, 140)):
    from PIL import Image, ImageDraw, ImageFont

    image = Image.new("RGB", size, "white")
    try:
        font = ImageFont.truetype("arial.ttf", 40)
    except OSError:
        font = ImageFont.load_default()
    ImageDraw.Draw(image).text((20, 40), text, fill="black", font=font)
    return image


def _echo() -> EchoProvider:
    return EchoProvider(responses={"vision": [VISION]})


# --- read -----------------------------------------------------------------------------------------


def test_text_in_an_image_is_read_as_lines() -> None:
    lines = media.read_text(_picture("Shipment 4821 arrived 14 September"))
    assert lines and "4821" in lines[0] and "September" in lines[0]


# --- see ------------------------------------------------------------------------------------------


async def test_what_an_image_shows_is_written_as_seen_lines() -> None:
    provider = _echo()
    lines = await media.see(_picture("x"), provider, name="crate.jpg")
    assert lines[0] == f"{SEEN_MARKER} (photo) A wooden crate on a loading dock, its lid split."
    assert f"{SEEN_MARKER} The crate is stencilled 4821" in lines
    assert lines[-1].startswith(f"{SEEN_MARKER} unclear:")
    assert all(is_seen_line(line) for line in lines)
    # The call carried the image and went to the vision model, not the text model.
    (call,) = provider.calls
    assert call.role == "vision" and len(call.images) == 1
    assert call.model == get_settings().vision_model


async def test_an_image_is_read_and_seen_then_cached(tmp_path: Path) -> None:
    path = tmp_path / "dock.png"
    _picture("DOCK 7 BAY 2").save(path)
    provider = _echo()
    await prepare([path], provider)

    document = parse(path)
    assert document.has_text
    assert any("DOCK" in line and not is_seen_line(line) for line in document.text.splitlines())
    assert f"{SEEN_MARKER} A forklift stands beside it" in document.text
    # Understood once: a second preparation reads the cache and calls nothing.
    await prepare([path], provider)
    assert len(provider.calls) == 1
    assert list((tmp_path / "media-cache").glob("*.json"))


async def test_without_understanding_an_image_says_why_it_has_no_text(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(get_settings(), "media_understanding", False)
    path = tmp_path / "dock.png"
    _picture("DOCK 7").save(path)
    await prepare([path], _echo())
    document = parse(path)
    assert not document.has_text
    assert "MEDIA_UNDERSTANDING" in document.text


# --- scanned PDFs -------------------------------------------------------------------------------


async def test_a_scanned_pdf_page_is_read_by_ocr(tmp_path: Path) -> None:
    path = tmp_path / "scan.pdf"
    _picture("Approved budget INR 380000", (900, 300)).save(path, format="PDF")
    before = parse(path)
    assert "(no extractable text on this page)" in before.text

    await prepare([path], _echo())
    after = parse(path)
    assert "(read by OCR: this page has no text layer)" in after.text
    assert "380000" in after.text.replace(",", "")
    assert after.page_starts == [1]


# --- hear, and video ----------------------------------------------------------------------------


async def test_audio_becomes_timed_lines(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        media,
        "transcribe",
        lambda _path: [(1.0, "Shipment 4821 arrived."), (65.2, "Rahul signed.")],
    )
    path = tmp_path / "call.wav"
    path.write_bytes(b"RIFF")
    await prepare([path], _echo())
    document = parse(path)
    assert document.has_text and document.kind == "audio"
    assert "[00:00:01] Shipment 4821 arrived." in document.text
    assert "[00:01:05] Rahul signed." in document.text


def _video(path: Path, seconds: int = 3) -> Path:
    import av

    with av.open(str(path), "w") as container:
        stream = container.add_stream("mpeg4", rate=1)
        stream.width, stream.height = 720, 140
        stream.pix_fmt = "yuv420p"
        for second in range(seconds):
            frame = av.VideoFrame.from_image(_picture(f"GATE {second + 1}"))
            for packet in stream.encode(frame):
                container.mux(packet)
        for packet in stream.encode():
            container.mux(packet)
    return path


async def test_a_video_is_a_timeline_of_on_screen_text_and_what_frames_show(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(get_settings(), "video_frame_every_s", 2.0)
    path = _video(tmp_path / "gate.mp4")
    await prepare([path], _echo())
    lines = parse(path).text.splitlines()

    on_screen = [line for line in lines if "(on screen)" in line]
    seen = [line for line in lines if is_seen_line(line)]
    assert on_screen and on_screen[0].startswith("[00:00:00] (on screen) GATE")
    assert seen
    # Frames are sampled at the interval, and bounded.
    assert len({line[:10] for line in on_screen}) <= get_settings().max_video_frames


async def test_a_persons_transcript_is_preferred_to_speech_recognition(tmp_path: Path) -> None:
    path = _video(tmp_path / "gate.mp4", seconds=1)
    (tmp_path / "gate.srt").write_text(
        "1\n00:00:00,500 --> 00:00:02,000\nOpen gate one.\n", encoding="utf-8"
    )
    await prepare([path], _echo())
    text = parse(path).text
    assert "(speech from the transcript gate.srt)" in text
    assert "[00:00:00.500] Open gate one." in text
    assert "(on screen)" in text  # what the frames showed is kept beside it


# --- seen is weaker evidence ------------------------------------------------------------------


def test_a_value_found_only_on_a_seen_line_is_not_grounded() -> None:
    chunk = Chunk(
        document_id="dock.png",
        lines=((3, "DOCK 7 BAY 2"), (4, f"{SEEN_MARKER} The crate is stencilled 4821")),
    )
    assert ground("4821", 4, chunk) == (4, False)
    assert ground("BAY 2", 3, chunk) == (3, True)


def _finding(*sources: str) -> Finding:
    return Finding(
        finding_id="F-001",
        claim="The crate for shipment 4821 was damaged.",
        evidence=[
            EvidenceRef(
                locator=SourceLocator(
                    document_id=s.split(":")[0],
                    document_name=s.split(":")[0],
                    row=int(s.split(":r")[1]),
                ),
                resolution=ResolutionStatus.RESOLVED,
            )
            for s in sources
        ],
    )


def test_a_finding_resting_only_on_what_was_seen_is_not_fully_supported() -> None:
    text = {
        "dock.png:r4": f"dock.png:r4: {SEEN_MARKER} (photo) A wooden crate, its lid split.",
        "report.txt:r2": "report.txt:r2: Crate 4821 arrived damaged.",
    }
    supported = VerificationResult(status=VerificationStatus.SUPPORTED, confidence=0.9)

    only_seen = described_only(_finding("dock.png:r4"), text, supported)
    assert only_seen.status is VerificationStatus.PARTIALLY_SUPPORTED
    assert [i.issue_type for i in only_seen.issues] == [IssueType.DESCRIBED_ONLY]

    with_text = described_only(_finding("dock.png:r4", "report.txt:r2"), text, supported)
    assert with_text.status is VerificationStatus.SUPPORTED


def test_the_vision_role_has_its_own_model() -> None:
    from app.core.agent_config import get_models_config

    config = get_models_config()
    assert config.params_for("vision").model == get_settings().vision_model
    assert config.params_for("reasoning").model == get_settings().ollama_model


async def test_a_failing_vision_model_never_loses_what_was_read(tmp_path: Path) -> None:
    """The bug found writing these tests: one failed vision call discarded the whole video."""
    path = _video(tmp_path / "gate.mp4", seconds=1)
    broken = EchoProvider(responses={"vision": ["not json at all"]})
    await prepare([path], broken)
    text = parse(path).text
    assert "(on screen) GATE" in text
    assert SEEN_MARKER not in text


def test_audio_is_decoded_to_16khz_mono_for_speech_recognition(tmp_path: Path) -> None:
    """Our decoder, not faster-whisper's: theirs passes PyAV 19 an option it no longer accepts."""
    import math
    import struct
    import wave

    path = tmp_path / "tone.wav"
    with wave.open(str(path), "wb") as out:
        out.setnchannels(2)
        out.setsampwidth(2)
        out.setframerate(44100)
        frames = b"".join(struct.pack("<hh", int(8000 * math.sin(i / 20)), 0) for i in range(44100))
        out.writeframes(frames)
    samples = media._decode_audio(path)
    assert samples.dtype.name == "float32"
    assert abs(samples.size - 16000) < 400  # one second at 16 kHz
