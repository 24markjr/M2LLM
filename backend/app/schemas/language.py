"""Languages a document was written in, and how it was read in English (v4 Phase 6).

The original stays the evidence. A document in an Indian language is read through a line-aligned
English translation - line N of the translation is line N of the original - so a citation's line
number points at the same line in both, and the viewer shows them side by side.
"""

from __future__ import annotations

from pydantic import Field

from app.schemas.common import JarvisModel

# A translated line starts with this marker and the source language, e.g. `[translated:hi] ...`.
# Like the `[seen]` marker (Phase 39) it says the line is a model's rendering, not source text: a
# finding whose every citation is such a line needs a person to confirm the translation.
TRANSLATED_MARKER = "[translated:"


def is_translated_line(text: str) -> bool:
    """Whether a line of document text is a machine translation rather than the source's words."""
    return TRANSLATED_MARKER in text


class Language(JarvisModel):
    """One language JARVIS can read: its ISO 639-1 code, names, script and FLORES-200 tag."""

    code: str
    name: str
    native: str
    script: str
    # The tag IndicTrans2 and Bhashini's pipelines name it by, e.g. `hin_Deva`.
    flores: str
    # The BCP-47 tag a browser's speech synthesis takes, e.g. `hi-IN`.
    speech: str = ""


class DocumentLanguage(JarvisModel):
    """How one document was read: its language and, if it was translated, by what and where."""

    language: str
    language_name: str = ""
    # The engine that translated it, e.g. `indictrans2`, and that engine's pinned version.
    engine: str = ""
    engine_version: str = ""
    # The document as written. The text a mission reads is its English translation.
    original_text: str = ""
    translated_lines: list[int] = Field(default_factory=list)
    # Lines whose figures did not all survive translation; the original's figures are appended to
    # them, and a reader is told to check them against the original.
    unsafe_lines: list[int] = Field(default_factory=list)
    # Lines left untranslated because the document was longer than one translation may run.
    untranslated_lines: int = 0

    @property
    def translated(self) -> bool:
        return bool(self.translated_lines)
