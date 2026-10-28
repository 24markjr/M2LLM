"""IndicTrans2 (AI4Bharat), the open-source translation engine, on the CPU (v4 Phase 6).

The distilled 200M models, converted for CTranslate2 - the runtime faster-whisper already uses - so
translation needs no PyTorch, runs in the backend container beside the API, and never competes with
the language model for the GPU. Measured on the laptop CPU, int8: about a tenth of a second a line.

Two models, one per direction: Indian languages to English (every evidence document), and English to
Indian languages (answers in the user's language, Phase 7). Each is pinned to a repository revision,
and that revision is the engine version a receipt records.

IndicTrans2 reads every Brahmic script as Devanagari - its training data was script-unified - and
writes Devanagari for every Indian target. The scripts' Unicode blocks are parallel, so converting
is an offset (`detect.BRAHMIC_BLOCKS`); without it Tamil text reaches the model as single letters.
"""

from __future__ import annotations

import re
import threading
from pathlib import Path
from typing import Any

from app.core.config import get_settings
from app.core.logging import get_logger
from app.language.detect import BRAHMIC_BLOCKS
from app.schemas.language import Language

log = get_logger(__name__)

ENGINE_NAME = "indictrans2"
# Sentences per call to the translator: enough to use the CPU's threads, few enough to bound memory.
BATCH = 32
# Malayalam's chillu letters have no Devanagari counterpart at the same offset: each is a consonant
# with its vowel killed, which is how they are written in Devanagari.
_CHILLU = {"ൺ": "ण्", "ൻ": "न्", "ർ": "र्", "ൽ": "ल्", "ൾ": "ळ्", "ൿ": "क्"}
_JOINERS = re.compile("[‌‍]")
# Punctuation is spaced off words, as the models were trained - but not inside a figure: the comma
# in 4,20,000, the point in 3.5 and the slashes in 15/05/2026 stay where they are.
_PUNCT = re.compile(r"(?<!\d)[.,/]|[.,/](?!\d)|[;:!?()\[\]\"'।॥|]")
_SENTENCE = re.compile(r"(?<=[।॥.!?])\s+")


class TranslationUnavailable(RuntimeError):
    """The engine cannot run here: a library or the model is missing. Never a content problem."""


def to_devanagari(text: str, script: str) -> str:
    base = BRAHMIC_BLOCKS.get(script)
    if base is None or base == 0x0900:
        return text
    out = []
    for ch in text:
        if ch in _CHILLU:
            out.append(_CHILLU[ch])
            continue
        offset = ord(ch) - base
        # Dandas are shared: every Brahmic script writes Devanagari's.
        shared = offset in (0x64, 0x65)
        out.append(chr(0x0900 + offset) if 0 <= offset < 0x80 and not shared else ch)
    return "".join(out)


def from_devanagari(text: str, script: str) -> str:
    base = BRAHMIC_BLOCKS.get(script)
    if base is None or base == 0x0900:
        return text
    out = []
    for ch in text:
        offset = ord(ch) - 0x0900
        shared = offset in (0x64, 0x65)
        out.append(chr(base + offset) if 0 <= offset < 0x80 and not shared else ch)
    return "".join(out)


def _rejoin(text: str) -> str:
    """Hyphens the model spaced out inside dates and identifiers: measured, `2026-06-02` came back
    as "2026 - 06 - 02" and `F-001` as "F - 001"."""
    return re.sub(r"(?<=[\dA-Z])\s+-\s+(?=\d)", "-", text)


def _detokenize_english(text: str) -> str:
    text = _rejoin(text)
    text = re.sub(r"\s+([.,;:!?%)\]])", r"\1", text)
    text = re.sub(r"([(\[])\s+", r"\1", text)
    # "₹ 3,80,000" -> "₹3,80,000": the figure is then one token, as the original wrote it.
    text = re.sub(r"([₹$€£])\s+(?=\d)", r"\1", text).strip()
    # A list number keeps its space: "1.The" -> "1. The".
    return re.sub(r"^(\d+)\.(?=[A-Za-z])", r"\1. ", text)


def sentences_of(line: str) -> list[str]:
    """A line's sentences. A full stop after a short word is an abbreviation, not an end - `Rs.`,
    `ரூ.`, `रु.`, `No.` - and one before a figure is part of it: measured, splitting `ரூ. 45,000`
    turned "priced at Rs. 45,000" into "priced at Rs. It was set at 45,000"."""
    pieces = [p for p in _SENTENCE.split(line.strip()) if p.strip()]
    out: list[str] = []
    for piece in pieces:
        if out:
            last_word = out[-1].rsplit(" ", 1)[-1]
            abbreviation = last_word.endswith(".") and len(last_word.rstrip(".")) <= 3
            if abbreviation or piece[:1].isdigit():
                out[-1] = f"{out[-1]} {piece}"
                continue
        out.append(piece)
    return out


class _Direction:
    """One model: a translator, the source tokenizer, and the directory they came from."""

    def __init__(self, repo: str, revision: str) -> None:
        self.repo = repo
        self.revision = revision
        self._translator: Any = None
        self._tokenizer: Any = None
        self._lock = threading.Lock()

    @property
    def version(self) -> str:
        return f"{self.repo}@{self.revision[:12]}" if self.revision else self.repo

    def _model_dir(self) -> Path:
        from huggingface_hub import snapshot_download

        root = Path(snapshot_download(self.repo, revision=self.revision or None))
        found = next((p.parent for p in root.rglob("model.bin")), None)
        if found is None:
            raise TranslationUnavailable(f"{self.repo} holds no CTranslate2 model.bin")
        return found

    def load(self) -> tuple[Any, Any]:
        with self._lock:
            if self._translator is None:
                try:
                    import ctranslate2
                    import sentencepiece
                except ImportError as exc:
                    raise TranslationUnavailable(
                        "translation needs the media extra: pip install '.[media]'"
                    ) from exc
                try:
                    directory = self._model_dir()
                except TranslationUnavailable:
                    raise
                except Exception as exc:
                    raise TranslationUnavailable(f"{self.repo}: {exc}") from exc
                self._translator = ctranslate2.Translator(
                    str(directory),
                    device="cpu",
                    compute_type="int8",
                    intra_threads=get_settings().translation_threads,
                )
                self._tokenizer = sentencepiece.SentencePieceProcessor(
                    model_file=str(directory / "vocab" / "model.SRC")
                )
                log.info("translation_model_loaded", model=self.version)
            return self._translator, self._tokenizer

    def run(self, sentences: list[str], source_tag: str, target_tag: str) -> list[str]:
        translator, tokenizer = self.load()
        out: list[str] = []
        for start in range(0, len(sentences), BATCH):
            batch = [
                [source_tag, target_tag, *tokenizer.encode(s, out_type=str)]
                for s in sentences[start : start + BATCH]
            ]
            with self._lock:
                results = translator.translate_batch(
                    batch, beam_size=4, max_input_length=512, max_decoding_length=512
                )
            out += ["".join(r.hypotheses[0]).replace("▁", " ").strip() for r in results]
        return out


class IndicTrans2:
    """Translation between English and the Indian languages IndicTrans2 covers."""

    name = ENGINE_NAME

    def __init__(self) -> None:
        settings = get_settings()
        self._to_english = _Direction(
            settings.translation_model, settings.translation_model_revision
        )
        self._from_english = _Direction(
            settings.translation_model_en_indic, settings.translation_model_en_indic_revision
        )

    def version(self, target: str = "en") -> str:
        return (self._to_english if target == "en" else self._from_english).version

    def translate(self, lines: list[str], source: Language, target: Language) -> list[str]:
        """Each line translated, in order: one output line per input line, blank for blank.

        A line is split into sentences, which are translated in batches and joined again, so a long
        paragraph is never cut at the model's input limit and the line alignment always holds.
        """
        if source.code == target.code:
            return list(lines)
        to_english = target.code == "en"
        if not to_english and source.code != "en":
            raise TranslationUnavailable("IndicTrans2 here translates to or from English only")
        direction = self._to_english if to_english else self._from_english

        pieces: list[list[str]] = []
        for line in lines:
            sentences = sentences_of(line)
            pieces.append(sentences)
        flat = [self._prepare(s, source) for sentences in pieces for s in sentences]
        translated = direction.run(flat, source.flores, target.flores) if flat else []

        out: list[str] = []
        cursor = 0
        for sentences in pieces:
            done = translated[cursor : cursor + len(sentences)]
            cursor += len(sentences)
            text = " ".join(done)
            out.append(_detokenize_english(text) if to_english else self._finish(text, target))
        return out

    @staticmethod
    def _prepare(sentence: str, source: Language) -> str:
        text = _JOINERS.sub("", sentence)
        text = to_devanagari(text, source.script)
        return re.sub(r"\s+", " ", _PUNCT.sub(lambda m: f" {m.group(0)} ", text)).strip()

    @staticmethod
    def _finish(text: str, target: Language) -> str:
        text = re.sub(r"\s+([.,;:!?।॥%)\]])", r"\1", _rejoin(text))
        return from_devanagari(re.sub(r"([(\[])\s+", r"\1", text), target.script).strip()


_engine: IndicTrans2 | None = None


def get_indictrans() -> IndicTrans2:
    global _engine
    if _engine is None:
        _engine = IndicTrans2()
    return _engine
