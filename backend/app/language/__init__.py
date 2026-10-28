"""The language layer: one interface to detect, translate, transcribe, speak and transliterate.

Two engines stand behind it (v4 Phases 6-7):

- **open-source**, always available: script-based detection, IndicTrans2 for translation (CPU,
  `indictrans.py`), faster-whisper for speech, the browser's own voices for reading aloud, and the
  local language model for Roman-script questions. It runs in our cloud, so it serves everything.
- **bhashini**, optional: MeitY's platform (`integrations/bhashini.py`), for what the
  organisation allows.

`routing.engines_for` decides which may serve a request, by the material's sensitivity and the
organisation's policy; when Bhashini fails, the open-source engine answers instead and the usage log
says it was a fallback. Whatever answered is named - in the receipt, the report and the viewer - and
the English is always the verified master: a translation is labelled as one.
"""

from __future__ import annotations

import asyncio
import time
from functools import partial

from app.core.config import get_settings
from app.core.logging import get_logger
from app.integrations.bhashini import BhashiniError, get_bhashini
from app.language.detect import ENGLISH, LANGUAGES, detect
from app.language.evidence import (
    apply,
    needs_translation,
    translate_text,
    translate_text_sync,
    unread,
)
from app.language.indictrans import ENGINE_NAME as OPEN_SOURCE_TRANSLATOR
from app.language.indictrans import TranslationUnavailable, get_indictrans
from app.language.routing import BHASHINI, OPEN_SOURCE, engines_for
from app.language.usage import record_usage
from app.schemas.common import JarvisModel
from app.schemas.evidence_locker import EvidenceClassification
from app.schemas.language import Language
from app.tools.loader import LoadedDocument

log = get_logger(__name__)

__all__ = [
    "ENGLISH",
    "LANGUAGES",
    "Translation",
    "TranslationUnavailable",
    "detect",
    "prepare_translation",
    "read_in_english",
    "translate",
]


class Translation(JarvisModel):
    """Translated lines, and what translated them."""

    lines: list[str]
    source: str
    target: str
    engine: str
    engine_version: str
    # Bhashini was allowed and tried, failed, and the open-source engine answered instead.
    fallback: bool = False

    @property
    def text(self) -> str:
        return "\n".join(self.lines)


def _open_source(lines: list[str], source: Language, target: Language) -> list[str]:
    return get_indictrans().translate(lines, source, target)


async def translate(
    lines: list[str],
    source: Language,
    target: Language,
    *,
    sensitivity: EvidenceClassification | None = None,
) -> Translation:
    """Translate line by line with the first engine the routing policy allows that answers."""
    if source.code == target.code:
        return Translation(
            lines=list(lines),
            source=source.code,
            target=target.code,
            engine="none",
            engine_version="",
        )
    fallback = False
    for engine in engines_for(sensitivity):
        if engine == BHASHINI:
            try:
                out = await get_bhashini().translate(lines, source, target)
            except BhashiniError as exc:
                log.warning("bhashini_failed_fallback", error=str(exc))
                fallback = True
                continue
            return Translation(
                lines=out,
                source=source.code,
                target=target.code,
                engine=BHASHINI,
                engine_version=get_bhashini().version(target.code),
            )
        started = time.perf_counter()
        out = await asyncio.to_thread(_open_source, lines, source, target)
        record_usage(
            engine=OPEN_SOURCE_TRANSLATOR,
            task="translation",
            source=source.code,
            target=target.code,
            amount=sum(len(x) for x in lines),
            unit="characters",
            ms=int((time.perf_counter() - started) * 1000),
            ok=True,
            fallback=fallback,
        )
        return Translation(
            lines=out,
            source=source.code,
            target=target.code,
            engine=OPEN_SOURCE_TRANSLATOR,
            engine_version=get_indictrans().version(target.code),
            fallback=fallback,
        )
    raise TranslationUnavailable("no language engine is allowed for this material")


def read_in_english(document: LoadedDocument) -> LoadedDocument:
    """A loaded document as a mission reads it: unchanged if it is English, else its line-aligned
    English translation with the original kept beside it (`evidence.py`). A translation made at
    upload is read from the cache; otherwise the open-source engine translates it now. Never raises:
    a document that cannot be translated is read as written, and says why."""
    if not get_settings().translate_evidence or not needs_translation(document.text):
        return document
    try:
        indictrans = get_indictrans()
        entry = translate_text_sync(
            document.text, OPEN_SOURCE_TRANSLATOR, indictrans.version("en"), _open_source
        )
    except TranslationUnavailable as exc:
        return unread(document, str(exc))
    if not entry.lines:
        return document
    return apply(document, entry)


async def prepare_translation(text: str, sensitivity: EvidenceClassification | None = None) -> None:
    """Translate a document's text ahead of being read, with the engine routing allows. Run at
    upload and before a mission, so `read_in_english` finds it cached. Never raises."""
    if not get_settings().translate_evidence or not needs_translation(text):
        return
    for engine in engines_for(sensitivity):
        try:
            if engine == BHASHINI:
                bhashini = get_bhashini()
                version = partial(bhashini.version, "en")
                await translate_text(text, BHASHINI, version, bhashini.translate)
            else:
                indictrans = get_indictrans()
                await asyncio.to_thread(
                    translate_text_sync,
                    text,
                    OPEN_SOURCE_TRANSLATOR,
                    indictrans.version("en"),
                    _open_source,
                )
            return
        except BhashiniError as exc:
            log.warning("bhashini_failed_fallback", error=str(exc))
        except TranslationUnavailable as exc:
            log.warning("translation_unavailable", error=str(exc))
            return


def language(code: str) -> Language:
    return LANGUAGES.get(code, ENGLISH)


def engine_status() -> dict[str, object]:
    """What each engine can do here, for the console and the admin guide."""
    from app.ops.governance import policy

    indictrans = get_indictrans()
    return {
        "engines": {
            OPEN_SOURCE: {
                "translation": indictrans.version("en"),
                "translation_from_english": indictrans.version("hi"),
                "speech_to_text": f"faster-whisper {get_settings().whisper_model}",
                "text_to_speech": "the browser's own voices",
                "transliteration": f"local model {get_settings().ollama_model}",
            },
            BHASHINI: {"configured": get_bhashini().configured()},
        },
        "bhashini_policy": policy().bhashini,
        "translate_evidence": get_settings().translate_evidence,
    }
