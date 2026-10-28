"""Asking and answering in Indian languages (v4 Phase 7).

A question can be typed in its own script (`कितना भुगतान हुआ?`), typed in Roman letters
(`kitna bhugtan hua?`) or spoken (`/language/transcribe` turns speech into text first). It is read
in English - the investigation's language, where every claim is verified against the evidence - and
the answer is given in English and in the person's language. **English stays the verified master:**
the translation is labelled as a machine translation of the verified answer, and names its engine.

Routing (`app/language/routing.py`) decides which engine may translate: the case is as sensitive as
its most sensitive file, so a question about Confidential evidence never leaves our cloud.
"""

from __future__ import annotations

import re
import time

from app.conversation.models import Turn, TurnTranslation
from app.conversation.tools import CaseMaterial
from app.core.logging import get_logger
from app.integrations.bhashini import BhashiniError, get_bhashini
from app.language import LANGUAGES, TranslationUnavailable, detect, translate
from app.language.detect import ENGLISH
from app.language.evidence import checked, needs_translation
from app.language.routing import BHASHINI, engines_for, strictest
from app.language.usage import record_usage
from app.llm.prompts import get_prompt_library
from app.llm.provider import LLMProvider
from app.llm.structured import generate_structured
from app.schemas.common import JarvisModel
from app.schemas.evidence_locker import EvidenceClassification
from app.schemas.language import Language

log = get_logger(__name__)

LABEL = "Machine translation of the verified English answer"

_WORD = re.compile(r"[a-z]+")
# Common words of Hindi typed in Roman letters, and of English. A message in a language the person
# chose is read as Roman-script Hindi when more of its words are the first kind than the second.
_ROMAN_HINDI = frozenset(
    "hai hain kya kitna kitni kitne kab kaun kyun kyon nahi nahin mein me ka ki ke ko se tha thi "
    "gaya gayi gaye diya di kiya ki aur ya par yeh ye woh wo kaise kahan paisa paise bhugtan "
    "rashi raashi tarikh tareekh hua hui hue karo batao bataiye dikhao kripya jo sab koi kis "
    "kisne liye wala wali waale tak bhi abhi kuch".split()
)
_ENGLISH = frozenset(
    "the is was were what which who when how did does do of and to in for on with by from that "
    "this are be been has have any all".split()
)


class Transliterated(JarvisModel):
    """What the transliteration prompt returns (`.agent/prompts/transliteration.md`)."""

    text: str


def looks_roman(text: str, language: Language) -> bool:
    """Whether `text`, with no Indian script in it, is `language` typed in Roman letters."""
    if language.code == "en" or needs_translation(text):
        return False
    words = _WORD.findall(text.lower())
    if not words:
        return False
    english = sum(w in _ENGLISH for w in words)
    if language.code == "hi":
        return sum(w in _ROMAN_HINDI for w in words) > english
    # No word list for the other languages: a message the person marked as theirs is theirs,
    # unless it reads as English.
    return english / len(words) < 0.2


def sensitivity_of(material: CaseMaterial) -> EvidenceClassification | None:
    levels: list[EvidenceClassification | None] = [
        EvidenceClassification(s) for s in material.sensitivities
    ]
    return strictest(levels)


async def transliterate(
    text: str,
    language: Language,
    provider: LLMProvider,
    sensitivity: EvidenceClassification | None,
) -> tuple[str, str]:
    """Roman-script text in the language's own script, and the engine that wrote it."""
    if BHASHINI in engines_for(sensitivity):
        try:
            return await get_bhashini().transliterate(text, language), BHASHINI
        except BhashiniError as exc:
            log.warning("bhashini_failed_fallback", task="transliteration", error=str(exc))
    script = {
        "Deva": "Devanagari",
        "Beng": "Bengali",
        "Taml": "Tamil",
        "Telu": "Telugu",
        "Knda": "Kannada",
        "Mlym": "Malayalam",
        "Gujr": "Gujarati",
        "Guru": "Gurmukhi",
        "Orya": "Odia",
        "Arab": "Urdu (Perso-Arabic)",
    }.get(language.script, language.script)
    prompt = (
        get_prompt_library()
        .get("transliteration")
        .render(language=language.name, script=script, text=text)
    )
    started = time.perf_counter()
    result = await generate_structured(provider, Transliterated, prompt, role="transliteration")
    engine = f"local model {provider.model_id}"
    record_usage(
        engine=engine,
        task="transliteration",
        source="en",
        target=language.code,
        amount=len(text),
        unit="characters",
        ms=int((time.perf_counter() - started) * 1000),
        ok=bool(result.text.strip()),
    )
    return result.text.strip(), engine


async def read_in_english(
    user: Turn, chosen: str, material: CaseMaterial, provider: LLMProvider
) -> None:
    """Put the person's message into English for the investigation, keeping what they typed.

    `chosen` is the language the person picked ("" to detect it). On success `user.text` is the
    English the model reads and `user.original_text` what was typed; an English message is left as
    it is. A message that cannot be translated is read as typed, and the turn says so.
    """
    typed = user.text
    hint = LANGUAGES.get(chosen) if chosen else None
    sensitivity = sensitivity_of(material)
    if needs_translation(typed):
        language = detect(typed)
    elif hint is not None and looks_roman(typed, hint):
        language = hint
        try:
            native, engine = await transliterate(typed, hint, provider, sensitivity)
        except Exception as exc:  # noqa: BLE001 - the message is still read, as typed
            log.warning("transliteration_failed", error=str(exc))
            user.language = hint.code
            user.language_note = "could not be transliterated; read as typed"
            return
        user.transliterated = native
        user.transliteration_engine = engine
        typed = native
    else:
        if hint is not None:
            user.language = hint.code  # answer in the chosen language, though asked in English
        return
    user.language = language.code
    try:
        english = await translate(typed.split("\n"), language, ENGLISH, sensitivity=sensitivity)
    except TranslationUnavailable as exc:
        user.language_note = f"not translated ({exc}); read as typed"
        return
    user.original_text = user.text
    user.text = english.text
    user.translation_engine = f"{english.engine} {english.engine_version}".strip()


async def answer_in_their_language(
    answer: Turn, language_code: str, material: CaseMaterial
) -> None:
    """Attach the answer in the person's language, labelled; the English stays the master."""
    language = LANGUAGES.get(language_code)
    if language is None or language.code == "en" or not answer.text.strip():
        return
    try:
        translated = await translate(
            answer.text.split("\n"), ENGLISH, language, sensitivity=sensitivity_of(material)
        )
    except TranslationUnavailable as exc:
        log.warning("answer_not_translated", language=language.code, error=str(exc))
        return
    answer.translation = TurnTranslation(
        language=language.code,
        language_name=language.name,
        speech=language.speech,
        # Every figure of the verified English must survive the translation, as on evidence.
        text="\n".join(
            checked(source, line)[0]
            for source, line in zip(answer.text.split("\n"), translated.lines, strict=True)
        ),
        engine=translated.engine,
        engine_version=translated.engine_version,
        fallback=translated.fallback,
        label=LABEL,
    )
