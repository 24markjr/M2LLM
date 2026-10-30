"""Evidence in Indian languages, read through a line-aligned English translation (v4 Phase 6).

**The original stays the evidence.** The file, its hash and its chain of custody are untouched; the
original text is kept beside the translation, and the viewer shows both. What a mission reads is the
translation, built so a citation means the same in both:

- **Line-aligned.** Line N of the translation is the translation of line N of the original.
  English lines, blank lines and page markers are copied as they are, so `report.pdf:r12` is line
  12 of both.
- **Marked.** Each translated line starts with `[translated:<code>]`. A finding whose every citation
  is such a line rests on machine translation alone and needs a person to confirm it
  (`integrations/verification.translated_only`); one that also cites an original line can be
  verified.
- **Figures checked.** Every number in the original line must appear in its translation. When one is
  missing or changed, the original's figures are appended to the line and it is listed as unsafe, so
  a mistranslated amount can never pass silently.

Translation runs once per text - when a file is uploaded or before a mission reads it - and is
cached by the text's SHA-256 in `.agent/media-cache/translations/`. A document longer than
`max_translated_lines` is translated up to that line and says how much was left as written.
"""

from __future__ import annotations

import hashlib
import re
import time
from collections.abc import Awaitable, Callable
from pathlib import Path

from pydantic import Field

from app.core.config import get_settings
from app.core.logging import get_logger
from app.language.detect import (
    ENGLISH,
    LANGUAGES,
    languages_by_script,
    line_script,
    to_ascii_digits,
)
from app.language.usage import record_usage
from app.schemas.common import JarvisModel
from app.schemas.language import DocumentLanguage, Language
from app.tools.loader import LoadedDocument

log = get_logger(__name__)

# Bumped when what this module writes changes, so an old cache entry is not reused.
PIPELINE_VERSION = 2  # 2: figures written as the original wrote them (`as_written`)
_ANY_INDIC = re.compile("[ऀ-෿؀-ۿ]")
_FIGURE = re.compile(r"\d[\d,]*(?:\.\d+)?")


class CachedTranslation(JarvisModel):
    text_sha256: str
    pipeline: int = PIPELINE_VERSION
    language: str
    engine: str
    engine_version: str
    # 1-based line number -> the line as the mission reads it, marker included.
    lines: dict[int, str] = Field(default_factory=dict)
    unsafe_lines: list[int] = Field(default_factory=list)
    untranslated_lines: int = 0


def needs_translation(text: str) -> bool:
    """Cheap first look: does any character belong to an Indian script at all?"""
    return bool(_ANY_INDIC.search(text))


def _cache_path(text_sha256: str) -> Path:
    return get_settings().agent_dir / "media-cache" / "translations" / f"{text_sha256}.json"


def _sha(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def cached_translation(text: str) -> CachedTranslation | None:
    path = _cache_path(_sha(text))
    if not path.is_file():
        return None
    try:
        found = CachedTranslation.model_validate_json(path.read_text(encoding="utf-8"))
    except ValueError:
        return None
    return found if found.pipeline == PIPELINE_VERSION else None


def _store(entry: CachedTranslation) -> None:
    path = _cache_path(entry.text_sha256)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(entry.model_dump_json(indent=1), encoding="utf-8")


def figures(text: str) -> list[str]:
    """The numbers in a text, as written, commas dropped: `₹3,80,000 on 15 May` -> 380000, 15."""
    return [m.group(0).replace(",", "").rstrip(".") for m in _FIGURE.finditer(text)]


def as_written(source: str, translated: str) -> str:
    """The translation with each figure written as the source wrote it.

    Measured on the VAJRA minutes: IndicTrans2 rendered ₹3,78,00,000 as "₹378,00,000" - the right
    value in a grouping no reader accepts, so the figure was read as 378, 00 and 000 and a correct
    overpayment could not be traced to it. A figure whose value is the source's is copied in the
    source's form; any other is left as the model wrote it, for `checked` to flag.
    """
    forms = {
        m.group(0).rstrip(",").replace(",", ""): m.group(0).rstrip(",")
        for m in _FIGURE.finditer(source)
    }

    def restore(match: re.Match[str]) -> str:
        written = match.group(0)
        trailing = "," if written.endswith(",") else ""
        bare = written.rstrip(",")
        return forms.get(bare.replace(",", ""), bare) + trailing

    return _FIGURE.sub(restore, translated)


def checked(original: str, translated: str) -> tuple[str, bool]:
    """The translated line, and whether its figures are the original's. When they are not, the
    original's figures are appended as written, so the evidence's numbers are always on the line.
    Either direction: an answer or a report translated into an Indian language is checked the same
    way against its English."""
    source = to_ascii_digits(original)
    translated = as_written(source, to_ascii_digits(translated))
    if sorted(figures(source)) == sorted(figures(translated)):
        return translated, True
    written = ", ".join(m.group(0) for m in _FIGURE.finditer(source)) or "none"
    return f"{translated} [figures in the original: {written}]", False


Translate = Callable[[list[str], Language, Language], Awaitable[list[str]]]
TranslateSync = Callable[[list[str], Language, Language], list[str]]


def _plan(text: str) -> tuple[list[str], dict[str, list[int]], dict[str, Language], int]:
    """The lines, which to translate grouped by language, and how many were left over the cap."""
    lines = text.split("\n")
    by_script = languages_by_script(text)
    todo: dict[str, list[int]] = {}
    budget = get_settings().max_translated_lines
    left = 0
    for index, line in enumerate(lines):
        script = line_script(line)
        if script is None:
            continue
        if budget <= 0:
            left += 1
            continue
        budget -= 1
        todo.setdefault(by_script[script].code, []).append(index)
    languages = {code: LANGUAGES[code] for code in todo}
    return lines, todo, languages, left


def _entry(
    text: str,
    lines: list[str],
    todo: dict[str, list[int]],
    results: dict[str, list[str]],
    engine: str,
    version: str,
    left: int,
) -> CachedTranslation:
    entry = CachedTranslation(
        text_sha256=_sha(text),
        language=max(todo.items(), key=lambda kv: len(kv[1]))[0],
        engine=engine,
        engine_version=version,
        untranslated_lines=left,
    )
    for code, indexes in todo.items():
        for index, translated in zip(indexes, results[code], strict=True):
            line, safe = checked(lines[index], translated)
            entry.lines[index + 1] = f"[translated:{code}] {line}"
            if not safe:
                entry.unsafe_lines.append(index + 1)
    entry.unsafe_lines.sort()
    return entry


def translate_text_sync(
    text: str, engine: str, version: str, run: TranslateSync
) -> CachedTranslation:
    """Translate (or fetch from cache) a document's text with a synchronous engine."""
    found = cached_translation(text)
    if found is not None:
        return found
    lines, todo, _languages, left = _plan(text)
    started = time.perf_counter()
    results = {
        code: run([to_ascii_digits(lines[i]) for i in indexes], LANGUAGES[code], ENGLISH)
        for code, indexes in todo.items()
    }
    entry = _entry(text, lines, todo, results, engine, version, left)
    record_usage(
        engine=engine,
        task="translation",
        source=entry.language,
        target="en",
        amount=sum(len(lines[i]) for ix in todo.values() for i in ix),
        unit="characters",
        ms=int((time.perf_counter() - started) * 1000),
        ok=True,
    )
    _store(entry)
    return entry


async def translate_text(
    text: str, engine: str, version: Callable[[], str], run: Translate
) -> CachedTranslation:
    """Translate (or fetch from cache) a document's text with an asynchronous engine."""
    found = cached_translation(text)
    if found is not None:
        return found
    lines, todo, _languages, left = _plan(text)
    results = {
        code: await run([to_ascii_digits(lines[i]) for i in indexes], LANGUAGES[code], ENGLISH)
        for code, indexes in todo.items()
    }
    entry = _entry(text, lines, todo, results, engine, version(), left)
    _store(entry)
    return entry


def apply(document: LoadedDocument, entry: CachedTranslation) -> LoadedDocument:
    """The document as a mission reads it: the translation, with the original kept beside it."""
    lines = document.text.split("\n")
    for number, line in entry.lines.items():
        if 0 < number <= len(lines):
            lines[number - 1] = line
    language = LANGUAGES.get(entry.language)
    reading = DocumentLanguage(
        language=entry.language,
        language_name=language.name if language else entry.language,
        engine=entry.engine,
        engine_version=entry.engine_version,
        original_text=document.text,
        translated_lines=sorted(entry.lines),
        unsafe_lines=list(entry.unsafe_lines),
        untranslated_lines=entry.untranslated_lines,
    )
    return document.model_copy(update={"text": "\n".join(lines), "reading": reading})


def unread(document: LoadedDocument, why: str) -> LoadedDocument:
    """A document in an Indian language that could not be translated: read as written, and said."""
    from app.language.detect import detect

    language = detect(document.text)
    log.warning("document_not_translated", document=document.document_id, reason=why)
    return document.model_copy(
        update={
            "reading": DocumentLanguage(
                language=language.code, language_name=language.name, original_text=""
            ),
            "omitted_note": (document.omitted_note + "; " if document.omitted_note else "")
            + f"not translated from {language.name}: {why}",
        }
    )
