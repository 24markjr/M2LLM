"""The language layer over HTTP (v4 Phases 6-7).

    GET  /language                  the languages offered, and what each engine can do here
    POST /language/translate        lines from one language to another (routed by sensitivity)
    POST /language/transliterate    Roman-script text into the language's own script
    POST /language/transcribe       a spoken question, as text, with the language heard
    POST /language/speak            an answer read aloud: audio from Bhashini, or 204 - use the
                                    browser's own voice (nothing leaves the device)
    GET  /ops/language-usage        calls, volume, failures and fallbacks by engine (admins)

A request naming a case is routed by the case's most sensitive file; one naming none is treated as
Confidential, so it never leaves our cloud.
"""

from __future__ import annotations

import asyncio
import tempfile
from pathlib import Path

from fastapi import APIRouter, Query, UploadFile, status
from fastapi.responses import Response
from pydantic import Field

from app.api.errors import ApiError
from app.conversation.language import sensitivity_of, transliterate
from app.conversation.tools import gather
from app.core.config import get_settings
from app.core.logging import get_logger
from app.integrations.bhashini import BhashiniError, get_bhashini
from app.language import (
    LANGUAGES,
    Translation,
    TranslationUnavailable,
    detect,
    engine_status,
    translate,
)
from app.language.routing import BHASHINI, engines_for
from app.language.usage import LanguageUsage, usage_summary
from app.llm import get_provider
from app.schemas.common import JarvisModel
from app.schemas.evidence_locker import EvidenceClassification
from app.schemas.language import Language

log = get_logger(__name__)

router = APIRouter(tags=["language"])

# A spoken question, not a recording to investigate: two minutes is plenty, and bounds the work.
MAX_QUESTION_BYTES = 8 * 1024 * 1024
MAX_QUESTION_SECONDS = 120


class LanguageCatalogue(JarvisModel):
    languages: list[Language]
    status: dict[str, object]


class TranslateRequest(JarvisModel):
    text: str = Field(min_length=1, max_length=20_000)
    # Empty: detect it.
    source: str = Field(default="", pattern=r"^[a-z]{0,3}$")
    target: str = Field(default="en", pattern=r"^[a-z]{2,3}$")
    case_id: str = Field(default="", max_length=64)


class TransliterateRequest(JarvisModel):
    text: str = Field(min_length=1, max_length=2000)
    language: str = Field(pattern=r"^[a-z]{2,3}$")
    case_id: str = Field(default="", max_length=64)


class Transliteration(JarvisModel):
    text: str
    language: str
    engine: str


class SpeakRequest(JarvisModel):
    text: str = Field(min_length=1, max_length=5000)
    language: str = Field(pattern=r"^[a-z]{2,3}$")
    case_id: str = Field(default="", max_length=64)


class Transcript(JarvisModel):
    text: str
    language: str
    language_name: str
    engine: str


def _language(code: str) -> Language:
    found = LANGUAGES.get(code)
    if found is None:
        raise ApiError(
            "UNSUPPORTED_LANGUAGE",
            f"no language {code!r}; one of {', '.join(sorted(LANGUAGES))}",
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
        )
    return found


async def _sensitivity(case_id: str) -> EvidenceClassification | None:
    return sensitivity_of(await gather(case_id)) if case_id else None


@router.get("/language", response_model=LanguageCatalogue)
async def catalogue() -> LanguageCatalogue:
    return LanguageCatalogue(languages=list(LANGUAGES.values()), status=engine_status())


@router.post("/language/translate", response_model=Translation)
async def translate_text(body: TranslateRequest) -> Translation:
    source = _language(body.source) if body.source else detect(body.text)
    target = _language(body.target)
    try:
        return await translate(
            body.text.split("\n"), source, target, sensitivity=await _sensitivity(body.case_id)
        )
    except TranslationUnavailable as exc:
        raise ApiError(
            "TRANSLATION_UNAVAILABLE", str(exc), status_code=status.HTTP_503_SERVICE_UNAVAILABLE
        ) from exc


@router.post("/language/transliterate", response_model=Transliteration)
async def transliterate_text(body: TransliterateRequest) -> Transliteration:
    language = _language(body.language)
    text, engine = await transliterate(
        body.text, language, get_provider(), await _sensitivity(body.case_id)
    )
    return Transliteration(text=text, language=language.code, engine=engine)


@router.post("/language/speak", response_model=None)
async def speak(body: SpeakRequest) -> Response:
    """Audio when Bhashini may serve this case; otherwise 204, and the browser reads it aloud with
    its own voice - nothing leaves the person's device."""
    language = _language(body.language)
    if BHASHINI in engines_for(await _sensitivity(body.case_id)):
        try:
            audio = await get_bhashini().speak(body.text, language)
            return Response(content=audio, media_type="audio/wav", headers={"X-Engine": BHASHINI})
        except BhashiniError as exc:
            log.warning("bhashini_failed_fallback", task="tts", error=str(exc))
    return Response(status_code=status.HTTP_204_NO_CONTENT, headers={"X-Engine": "browser"})


@router.post("/language/transcribe", response_model=Transcript)
async def transcribe(
    audio: UploadFile,
    language: str = Query(default="", pattern=r"^[a-z]{0,3}$"),
) -> Transcript:
    """A spoken question as text. faster-whisper on the CPU, told the language when the person
    chose one, else hearing it. The question is never kept: the file is deleted once read."""
    hint = _language(language) if language else None
    data = await audio.read(MAX_QUESTION_BYTES + 1)
    if len(data) > MAX_QUESTION_BYTES:
        raise ApiError(
            "QUESTION_TOO_LONG",
            "a spoken question is at most two minutes",
            status_code=status.HTTP_413_CONTENT_TOO_LARGE,
        )
    with tempfile.TemporaryDirectory() as folder:
        path = Path(folder) / "question.audio"
        path.write_bytes(data)
        try:
            text, heard = await asyncio.to_thread(_whisper, path, hint.code if hint else None)
        except ImportError as exc:
            raise ApiError(
                "SPEECH_UNAVAILABLE",
                "speech recognition needs the media extra: pip install '.[media]'",
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            ) from exc
    spoken = LANGUAGES.get(heard) or (hint or detect(text))
    return Transcript(
        text=text,
        language=spoken.code,
        language_name=spoken.name,
        engine=f"faster-whisper {get_settings().whisper_model}",
    )


def _whisper(path: Path, language: str | None) -> tuple[str, str]:
    from app.tools import media

    size = get_settings().whisper_model
    if size not in media._whisper_models:
        from faster_whisper import WhisperModel

        media._whisper_models[size] = WhisperModel(size, device="cpu", compute_type="int8")
    samples = media._decode_audio(path)[: MAX_QUESTION_SECONDS * 16000]
    segments, info = media._whisper_models[size].transcribe(
        samples, language=language, vad_filter=True
    )
    return " ".join(s.text.strip() for s in segments).strip(), str(info.language or "")


@router.get("/ops/language-usage", response_model=LanguageUsage)
async def language_usage(days: int = Query(default=30, ge=1, le=366)) -> LanguageUsage:
    return usage_summary(days)
