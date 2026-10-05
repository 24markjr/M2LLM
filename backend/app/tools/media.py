"""Seeing and hearing: what images, scans, video and audio contain (Phase 39).

Phase 38 accepted images and video and could say only their size. This module makes their
**content** available to an investigation, in three ways, all local:

- **Read**: text printed or written in an image, a scanned PDF page or a video frame. OCR, with
  PaddleOCR's models through RapidOCR (Member 2 chose PaddleOCR).
- **See**: what an image or frame shows - objects, condition, people and what they do, charts. The
  vision model `models.yaml:roles.vision` names (`qwen2.5vl:3b`), reached through `app/llm/`.
- **Hear**: what is said in a video or audio file, with timestamps. faster-whisper, on the CPU.

**Read and heard text is evidence; what is seen is an account.** OCR and speech recognition copy
what is there. A vision model describes, and can be wrong, so every line it writes carries the
`[seen]` marker (`schemas.evidence.SEEN_MARKER`): the knowledge layer never grounds a value on such
a line, and a finding whose evidence is only such lines cannot be fully supported.

**Understanding runs once per file.** It is slow (a vision call is seconds; a recording is
transcribed at a few times real time), so its result is cached by the file's SHA-256 in
`.agent/media-cache/` and the parser reads the cache. It runs when a file is uploaded, and before a
mission or an analysis that names a file not yet understood.

Everything is bounded (invariant 7): frames per video, seconds per recording, pages per PDF.
"""

from __future__ import annotations

import base64
import io
from pathlib import Path
from typing import Any

from pydantic import Field

from app.core.config import get_settings
from app.core.logging import get_logger
from app.llm.prompts import get_prompt_library
from app.llm.provider import LLMProvider
from app.llm.structured import generate_structured
from app.schemas.common import JarvisModel
from app.schemas.evidence import SEEN_MARKER

log = get_logger(__name__)

# Bumped when what this module writes changes, so an old cache entry is not reused for new output.
PIPELINE_VERSION = 1
# OCR results below this confidence are kept but marked, so a reader knows to doubt them.
LOW_OCR_CONFIDENCE = 0.6
# The longest side an image is sent to the vision model at. Larger costs time and adds nothing a
# 3B model can use.
VISION_MAX_SIDE = 1280
MAX_OCR_PAGES = 50

IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".gif", ".bmp", ".tif", ".tiff", ".webp"}
VIDEO_EXTENSIONS = {".mp4", ".mov", ".m4v", ".mkv", ".webm", ".avi"}
AUDIO_EXTENSIONS = {".mp3", ".wav", ".m4a", ".ogg", ".flac", ".aac"}


class VisualReading(JarvisModel):
    """What the vision model reports about one image (`.agent/prompts/vision.md`)."""

    kind: str = "other"
    summary: str = ""
    observations: list[str] = Field(default_factory=list, max_length=8)
    uncertain: list[str] = Field(default_factory=list)


class Understanding(JarvisModel):
    """What a file was understood to contain: citable lines, and how they were obtained."""

    sha256: str
    pipeline: int = PIPELINE_VERSION
    lines: list[str] = Field(default_factory=list)
    read_lines: int = 0
    seen_lines: int = 0
    heard_lines: int = 0
    # Which engines produced the lines, e.g. {"ocr": "rapidocr", "vision": "qwen2.5vl:3b"}.
    engines: dict[str, str] = Field(default_factory=dict)
    # For a PDF: the pages that had no text layer and were read by OCR, page number -> lines.
    pages: dict[int, list[str]] = Field(default_factory=dict)
    notes: list[str] = Field(default_factory=list)

    @property
    def has_text(self) -> bool:
        return bool(self.lines) or bool(self.pages)


# --- the cache ----------------------------------------------------------------------------------


def cache_dir() -> Path:
    return get_settings().agent_dir / "media-cache"


def cached(sha256: str) -> Understanding | None:
    path = cache_dir() / f"{sha256}.json"
    if not path.exists():
        return None
    try:
        found = Understanding.model_validate_json(path.read_text(encoding="utf-8"))
    except ValueError:
        return None
    return found if found.pipeline == PIPELINE_VERSION else None


def store(understanding: Understanding) -> None:
    directory = cache_dir()
    directory.mkdir(parents=True, exist_ok=True)
    (directory / f"{understanding.sha256}.json").write_text(
        understanding.model_dump_json(indent=2), encoding="utf-8"
    )


# --- read: OCR ----------------------------------------------------------------------------------

_ocr_engine: Any = None


def _ocr() -> Any:
    global _ocr_engine
    if _ocr_engine is None:
        from rapidocr_onnxruntime import RapidOCR

        _ocr_engine = RapidOCR()
    return _ocr_engine


def read_text(image: Any) -> list[str]:
    """The text in an image, one line per printed line, top to bottom.

    OCR returns boxes, not lines: boxes whose vertical centres are close are joined left to right.
    A line read with low confidence is kept and marked, never silently dropped.
    """
    import numpy as np

    result, _elapsed = _ocr()(np.array(image.convert("RGB")))
    if not result:
        return []
    boxes = []
    for points, text, confidence in result:
        ys = [p[1] for p in points]
        xs = [p[0] for p in points]
        boxes.append((sum(ys) / len(ys), min(xs), max(ys) - min(ys), str(text), float(confidence)))
    boxes.sort()
    rows: list[list[tuple[float, float, float, str, float]]] = []
    for box in boxes:
        if rows and abs(rows[-1][0][0] - box[0]) < max(box[2], rows[-1][0][2]) * 0.5:
            rows[-1].append(box)
        else:
            rows.append([box])
    lines = []
    for row in rows:
        row.sort(key=lambda b: b[1])
        text = " ".join(b[3] for b in row).strip()
        confidence = min(b[4] for b in row)
        if text:
            lines.append(
                text if confidence >= LOW_OCR_CONFIDENCE else f"{text} (low OCR confidence)"
            )
    return lines


# --- see: the vision model ----------------------------------------------------------------------


def _jpeg_b64(image: Any) -> str:
    picture = image.convert("RGB")
    picture.thumbnail((VISION_MAX_SIDE, VISION_MAX_SIDE))
    buffer = io.BytesIO()
    picture.save(buffer, format="JPEG", quality=85)
    return base64.b64encode(buffer.getvalue()).decode("ascii")


async def see(image: Any, provider: LLMProvider, *, name: str, context: str = "") -> list[str]:
    """`[seen]` lines: the vision model's account of one image. Empty if the model cannot answer."""
    # Any failure means nothing was seen, never that what was read or heard is lost: a video's
    # on-screen text and speech must survive a vision model that is missing or misbehaving.
    try:
        prompt = get_prompt_library().get("vision").render(name=name, context=context)
        reading = await generate_structured(
            provider, VisualReading, prompt, role="vision", images=[_jpeg_b64(image)]
        )
    except Exception as exc:  # noqa: BLE001 - degrade to "nothing seen", logged
        log.warning(
            "vision_failed", file=name, context=context, error=f"{type(exc).__name__}: {exc}"
        )
        return []
    lines = (
        [f"{SEEN_MARKER} ({reading.kind}) {reading.summary}".rstrip()] if reading.summary else []
    )
    lines += [f"{SEEN_MARKER} {item}" for item in reading.observations if item.strip()]
    if reading.uncertain:
        lines.append(f"{SEEN_MARKER} unclear: {'; '.join(reading.uncertain)}")
    return lines


# --- hear: speech to text -----------------------------------------------------------------------

_whisper_models: dict[str, Any] = {}


def transcribe(path: Path) -> list[tuple[float, str]]:
    """(start seconds, text) per spoken segment. Bounded by `max_media_seconds`."""
    settings = get_settings()
    size = settings.whisper_model
    if size not in _whisper_models:
        from faster_whisper import WhisperModel

        _whisper_models[size] = WhisperModel(size, device="cpu", compute_type="int8")
    segments, _info = _whisper_models[size].transcribe(_decode_audio(path), vad_filter=True)
    spoken = []
    for segment in segments:
        if segment.start > settings.max_media_seconds:
            break
        text = segment.text.strip()
        if text:
            spoken.append((float(segment.start), text))
    return spoken


def _decode_audio(path: Path) -> Any:
    """A file's audio as 16 kHz mono float samples, what Whisper expects. Bounded in length.

    Decoded here rather than by faster-whisper: its own decoder (1.2.1) passes PyAV an option that
    PyAV 19 removed, and fails on every file. Found by the Phase 39 live check; the unit tests stub
    speech recognition and could not see it.
    """
    import av
    import numpy as np

    limit = int(get_settings().max_media_seconds * 16000)
    chunks: list[Any] = []
    total = 0
    resampler = av.AudioResampler(format="flt", layout="mono", rate=16000)
    with av.open(str(path)) as container:
        stream = next((s for s in container.streams if s.type == "audio"), None)
        if stream is None:
            return np.zeros(0, dtype=np.float32)
        for frame in container.decode(stream):
            if not isinstance(frame, av.AudioFrame):
                continue
            for resampled in resampler.resample(frame):
                samples = resampled.to_ndarray().reshape(-1)
                chunks.append(samples)
                total += samples.size
            if total >= limit:
                break
    if not chunks:
        return np.zeros(0, dtype=np.float32)
    return np.concatenate(chunks)[:limit].astype(np.float32)


def _clock(seconds: float) -> str:
    whole = int(seconds)
    return f"{whole // 3600:02d}:{whole % 3600 // 60:02d}:{whole % 60:02d}"


# --- video frames -------------------------------------------------------------------------------


def sample_frames(path: Path) -> list[tuple[float, Any]]:
    """(seconds, image) at a fixed interval, at most `max_video_frames`."""
    import av

    settings = get_settings()
    frames: list[tuple[float, Any]] = []
    with av.open(str(path)) as container:
        stream = next((s for s in container.streams if s.type == "video"), None)
        if stream is None:
            return []
        next_at = 0.0
        for frame in container.decode(stream):
            if not isinstance(frame, av.VideoFrame):
                continue
            if frame.time is None or frame.time < next_at:
                continue
            frames.append((float(frame.time), frame.to_image()))  # type: ignore[no-untyped-call]  # PyAV leaves it unannotated
            next_at = frame.time + settings.video_frame_every_s
            if len(frames) >= settings.max_video_frames or frame.time > settings.max_media_seconds:
                break
    return frames


def _has_audio(path: Path) -> bool:
    import av

    with av.open(str(path)) as container:
        return any(s.type == "audio" for s in container.streams)


# --- understanding a file -----------------------------------------------------------------------


async def understand(path: Path, sha256: str, provider: LLMProvider) -> Understanding:
    """Read, see and hear one file, and cache what was found. Never raises for content problems."""
    import asyncio

    found = cached(sha256)
    if found is not None:
        return found
    suffix = path.suffix.lower()
    result = Understanding(sha256=sha256)
    try:
        if suffix in IMAGE_EXTENSIONS:
            await _understand_image(path, provider, result)
        elif suffix in VIDEO_EXTENSIONS:
            await _understand_video(path, provider, result)
        elif suffix in AUDIO_EXTENSIONS:
            spoken = await asyncio.to_thread(transcribe, path)
            result.lines = [f"[{_clock(t)}] {text}" for t, text in spoken]
            result.heard_lines = len(spoken)
            result.engines["speech"] = f"whisper-{get_settings().whisper_model}"
        elif suffix == ".pdf":
            await asyncio.to_thread(_ocr_scanned_pages, path, result)
    except ImportError as exc:
        # The optional extra is not installed: say exactly what would make this work.
        log.warning("media_libraries_missing", file=path.name, missing=str(exc))
        result.notes.append(
            f'understanding needs the media extra: pip install -e "backend[media]" ({exc.name})'
        )
    except Exception as exc:  # content problems degrade to "not understood", never to a crash
        log.exception("media_understanding_failed", file=path.name)
        result.notes.append(f"could not be understood: {type(exc).__name__}: {exc}")
    store(result)
    log.info(
        "media_understood",
        file=path.name,
        read=result.read_lines,
        seen=result.seen_lines,
        heard=result.heard_lines,
        engines=result.engines,
    )
    return result


async def _understand_image(path: Path, provider: LLMProvider, result: Understanding) -> None:
    import asyncio

    from PIL import Image, ImageOps

    with Image.open(path) as opened:
        image = ImageOps.exif_transpose(opened) or opened
        image.load()
    read = await asyncio.to_thread(read_text, image)
    seen = await see(image, provider, name=path.name)
    result.lines = read + seen
    result.read_lines, result.seen_lines = len(read), len(seen)
    result.engines["ocr"] = "rapidocr (PaddleOCR models)"
    if seen:
        result.engines["vision"] = get_settings().vision_model


async def _understand_video(path: Path, provider: LLMProvider, result: Understanding) -> None:
    """A timeline: what is said, what is on screen, and what is seen, ordered by time."""
    import asyncio

    timeline: list[tuple[float, int, str]] = []
    if await asyncio.to_thread(_has_audio, path):
        spoken = await asyncio.to_thread(transcribe, path)
        timeline += [(t, 0, text) for t, text in spoken]
        result.heard_lines = len(spoken)
        result.engines["speech"] = f"whisper-{get_settings().whisper_model}"
    frames = await asyncio.to_thread(sample_frames, path)
    for at, image in frames:
        on_screen = await asyncio.to_thread(read_text, image)
        timeline += [(at, 1, f"(on screen) {line}") for line in on_screen]
        result.read_lines += len(on_screen)
        seen = await see(image, provider, name=path.name, context=f"frame at {_clock(at)}")
        timeline += [(at, 2, line) for line in seen]
        result.seen_lines += len(seen)
    if frames:
        result.engines["ocr"] = "rapidocr (PaddleOCR models)"
        result.engines["vision"] = get_settings().vision_model
    timeline.sort(key=lambda item: (item[0], item[1]))
    result.lines = [f"[{_clock(at)}] {text}" for at, _order, text in timeline]
    result.notes.append(f"{len(frames)} frame(s) sampled")


def _ocr_scanned_pages(path: Path, result: Understanding) -> None:
    """OCR for the pages of a PDF that have no text layer (a scan)."""
    import pypdfium2 as pdfium
    from pypdf import PdfReader

    reader = PdfReader(str(path))
    blank = [
        number
        for number, page in enumerate(reader.pages[:MAX_OCR_PAGES], start=1)
        if not (page.extract_text() or "").strip()
    ]
    if not blank:
        return
    document = pdfium.PdfDocument(str(path))
    try:
        for number in blank:
            image = document[number - 1].render(scale=2).to_pil()
            lines = read_text(image)
            result.pages[number] = lines or ["(no text found on this page)"]
            result.read_lines += len(lines)
    finally:
        document.close()
    result.engines["ocr"] = "rapidocr (PaddleOCR models)"
    result.notes.append(f"OCR on {len(blank)} page(s) with no text layer")


def describe(understanding: Understanding) -> str:
    """One line for a header: how the content was obtained."""
    parts = []
    if understanding.read_lines:
        parts.append(f"{understanding.read_lines} line(s) read")
    if understanding.heard_lines:
        parts.append(f"{understanding.heard_lines} spoken segment(s) heard")
    if understanding.seen_lines:
        parts.append(
            f"{understanding.seen_lines} line(s) seen by "
            f"{understanding.engines.get('vision', 'a vision model')}"
        )
    return ", ".join(parts) or "nothing found"
