"""Which language a text is written in - by its script, deterministically (v4 Phase 6).

Indian scripts each have their own Unicode block, so most languages are known from the letters
alone: Tamil letters are Tamil. Three scripts are shared - Devanagari (Hindi, Marathi, Nepali),
Bengali (Bengali, Assamese) and Arabic (Urdu) - and those are told apart by a handful of words and
letters only one of the languages uses. No model is involved, so the answer is the same every time
and costs nothing; a language this cannot tell is read as the script's most common one.
"""

from __future__ import annotations

import re

from app.schemas.language import Language

ENGLISH = Language(
    code="en", name="English", native="English", script="Latn", flores="eng_Latn", speech="en-IN"
)

LANGUAGES: dict[str, Language] = {
    lang.code: lang
    for lang in [
        ENGLISH,
        Language(
            code="hi",
            name="Hindi",
            native="हिन्दी",
            script="Deva",
            flores="hin_Deva",
            speech="hi-IN",
        ),
        Language(
            code="mr",
            name="Marathi",
            native="मराठी",
            script="Deva",
            flores="mar_Deva",
            speech="mr-IN",
        ),
        Language(
            code="ne",
            name="Nepali",
            native="नेपाली",
            script="Deva",
            flores="npi_Deva",
            speech="ne-NP",
        ),
        Language(
            code="bn",
            name="Bengali",
            native="বাংলা",
            script="Beng",
            flores="ben_Beng",
            speech="bn-IN",
        ),
        Language(
            code="as",
            name="Assamese",
            native="অসমীয়া",
            script="Beng",
            flores="asm_Beng",
            speech="as-IN",
        ),
        Language(
            code="pa",
            name="Punjabi",
            native="ਪੰਜਾਬੀ",
            script="Guru",
            flores="pan_Guru",
            speech="pa-IN",
        ),
        Language(
            code="gu",
            name="Gujarati",
            native="ગુજરાતી",
            script="Gujr",
            flores="guj_Gujr",
            speech="gu-IN",
        ),
        Language(
            code="or", name="Odia", native="ଓଡ଼ିଆ", script="Orya", flores="ory_Orya", speech="or-IN"
        ),
        Language(
            code="ta", name="Tamil", native="தமிழ்", script="Taml", flores="tam_Taml", speech="ta-IN"
        ),
        Language(
            code="te",
            name="Telugu",
            native="తెలుగు",
            script="Telu",
            flores="tel_Telu",
            speech="te-IN",
        ),
        Language(
            code="kn",
            name="Kannada",
            native="ಕನ್ನಡ",
            script="Knda",
            flores="kan_Knda",
            speech="kn-IN",
        ),
        Language(
            code="ml",
            name="Malayalam",
            native="മലയാളം",
            script="Mlym",
            flores="mal_Mlym",
            speech="ml-IN",
        ),
        Language(
            code="ur", name="Urdu", native="اردو", script="Arab", flores="urd_Arab", speech="ur-IN"
        ),
    ]
}

# The first code point of each Brahmic script's block. The blocks are laid out in parallel, so a
# letter's offset from its block's start is the same letter in every script - which is what lets
# IndicTrans2 read every script as Devanagari (`app/language/indictrans.py`).
BRAHMIC_BLOCKS: dict[str, int] = {
    "Deva": 0x0900,
    "Beng": 0x0980,
    "Guru": 0x0A00,
    "Gujr": 0x0A80,
    "Orya": 0x0B00,
    "Taml": 0x0B80,
    "Telu": 0x0C00,
    "Knda": 0x0C80,
    "Mlym": 0x0D00,
}
_ARABIC = (0x0600, 0x06FF)

# The script's language when nothing says otherwise.
_DEFAULT_FOR_SCRIPT = {
    "Deva": "hi",
    "Beng": "bn",
    "Guru": "pa",
    "Gujr": "gu",
    "Orya": "or",
    "Taml": "ta",
    "Telu": "te",
    "Knda": "kn",
    "Mlym": "ml",
    "Arab": "ur",
}

# Words and letters only one language of a shared script uses, counted to tell them apart.
_MARKERS: dict[str, dict[str, re.Pattern[str]]] = {
    "Deva": {
        "hi": re.compile(r"(?:^|\s)(?:है|हैं|और|के|की|में|था|थी|गया|किया|नहीं)(?=[\s,।.]|$)"),
        "mr": re.compile(r"(?:^|\s)(?:आहे|आहेत|आणि|च्या|झाला|झाली|केले|नाही)(?=[\s,।.]|$)|ळ"),
        "ne": re.compile(r"(?:^|\s)(?:छ|छन्|भएको|गरेको|र|पनि|हुन्छ)(?=[\s,।.]|$)"),
    },
    "Beng": {
        "bn": re.compile(r"(?:^|\s)(?:এবং|হয়েছে|করা|না)(?=[\s,।.]|$)"),
        "as": re.compile(r"[ৰৱ]"),
    },
}

# A line is in an Indian language when at least this share of its letters are in an Indian script.
# Lower than a half, so a sentence naming a vendor or an invoice number in English still counts.
INDIC_SHARE = 0.25


def script_of_char(ch: str) -> str | None:
    cp = ord(ch)
    for script, base in BRAHMIC_BLOCKS.items():
        if base <= cp < base + 0x80:
            return script
    if _ARABIC[0] <= cp <= _ARABIC[1]:
        return "Arab"
    return None


def line_script(line: str) -> str | None:
    """The Indian script a line is written in, or None for English, figures or nothing."""
    counts: dict[str, int] = {}
    latin = 0
    for ch in line:
        script = script_of_char(ch)
        if script is not None:
            # Vowel signs are not `isalpha`, but they are letters; dandas and digits are not.
            base = BRAHMIC_BLOCKS.get(script)
            digit = base is not None and 0x64 <= ord(ch) - base <= 0x6F
            if not digit and (ch.isalpha() or base is not None):
                counts[script] = counts.get(script, 0) + 1
        elif ch.isascii() and ch.isalpha():
            latin += 1
    if not counts:
        return None
    script, indic = max(counts.items(), key=lambda kv: kv[1])
    total = indic + latin
    return script if indic >= 2 and indic / total >= INDIC_SHARE else None


def language_for_script(script: str, text: str) -> Language:
    """Which of a script's languages `text` is in."""
    markers = _MARKERS.get(script)
    code = _DEFAULT_FOR_SCRIPT.get(script, "hi")
    if markers:
        scores = {lang: len(pattern.findall(text)) for lang, pattern in markers.items()}
        best = max(scores.items(), key=lambda kv: kv[1])
        if best[1] > 0 and best[1] > scores.get(code, 0):
            code = best[0]
    return LANGUAGES[code]


def detect(text: str) -> Language:
    """The language most of `text`'s Indian-script lines are in; English when there are none."""
    by_script: dict[str, list[str]] = {}
    for line in text.splitlines():
        script = line_script(line)
        if script is not None:
            by_script.setdefault(script, []).append(line)
    if not by_script:
        return ENGLISH
    script, lines = max(by_script.items(), key=lambda kv: len(kv[1]))
    return language_for_script(script, "\n".join(lines))


def languages_by_script(text: str) -> dict[str, Language]:
    """Each Indian script in `text`, and the language its lines are in - for a mixed document."""
    by_script: dict[str, list[str]] = {}
    for line in text.splitlines():
        script = line_script(line)
        if script is not None:
            by_script.setdefault(script, []).append(line)
    return {s: language_for_script(s, "\n".join(lines)) for s, lines in by_script.items()}


def to_ascii_digits(text: str) -> str:
    """Indian-script and Arabic-Indic digits as 0-9. Translation models misread native digits:
    measured, Bengali `১৪ মে ২০২৬` came back as "May 6, 2013"."""
    out = []
    for ch in text:
        cp = ord(ch)
        script = script_of_char(ch)
        if script in BRAHMIC_BLOCKS and 0x66 <= cp - BRAHMIC_BLOCKS[script] <= 0x6F:
            out.append(chr(cp - BRAHMIC_BLOCKS[script] - 0x66 + 0x30))
        elif 0x0660 <= cp <= 0x0669 or 0x06F0 <= cp <= 0x06F9:
            out.append(chr((cp & 0x0F) + 0x30))
        else:
            out.append(ch)
    return "".join(out)
