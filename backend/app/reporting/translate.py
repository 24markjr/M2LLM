"""The report in an Indian language (v4 Phase 7): a labelled translation of the verified English.

The designed document (`document.py`) is translated string by string, in one batch, so screen and
Word match. What is evidence or an identifier is never translated: quotes from the documents stay
as written (a translated quote would no longer be a quote), and finding ids, locators, file names,
hashes and figures-only cells are copied. A banner names the engine and says the English report is
the master. The PDF is English only: ReportLab cannot shape Indian scripts, and a PDF whose
conjuncts fall apart would misquote the very words it translates.
"""

from __future__ import annotations

import re

from app.language import Translation, translate
from app.language.detect import ENGLISH
from app.language.evidence import checked
from app.reporting.document import Block, Cell, ReportDocument
from app.schemas.evidence_locker import EvidenceClassification
from app.schemas.language import Language

_LETTERS = re.compile(r"[A-Za-z]{2,}")
_HEX = re.compile(r"^[0-9a-f ]+$")


def _identifier(text: str) -> bool:
    return " " not in text.strip() and bool(re.search(r"[\d._:\-/@]", text))


def _translatable(text: str) -> bool:
    """Prose and labels; never an identifier (`F-001`, `report.txt:r12`, `run_ab12`), a list of
    them (a Sources cell: measured, `saraswati_milestone_register.txt:r8, ...` came back as
    "Saraswati @mlestone.register. txt: r8") or a hash."""
    if not _LETTERS.search(text) or _HEX.match(text):
        return False
    return not all(_identifier(part) for part in text.split(","))


class _Collector:
    """Gathers every translatable string, then puts each translation back where it came from."""

    def __init__(self) -> None:
        self.lines: list[str] = []

    def add(self, text: str) -> list[int]:
        if not _translatable(text):
            return []
        start = len(self.lines)
        self.lines += text.split("\n")
        return list(range(start, len(self.lines)))


def _put(text: str, slots: list[int], out: list[str]) -> str:
    return "\n".join(out[i] for i in slots) if slots else text


async def translated(
    document: ReportDocument,
    language: Language,
    sensitivity: EvidenceClassification | None,
) -> ReportDocument:
    """`document` in `language`, with the English kept as the master and the engine named."""
    collect = _Collector()
    title = collect.add(document.title)
    subtitle = collect.add(document.subtitle)
    facts = [(collect.add(k), collect.add(v)) for k, v in document.facts]
    blocks: list[tuple[Block, dict[str, object]]] = []
    for block in document.blocks:
        slots: dict[str, object] = {
            "text": collect.add(block.text),
            "items": [collect.add(i) for i in block.items],
            "columns": [collect.add(c) for c in block.columns],
            "rows": [[collect.add(c.text) for c in row] for row in block.rows],
            "facts": [(collect.add(k), collect.add(v)) for k, v in block.facts],
            # The quotes are the evidence's own words: only the side's label would be translated,
            # and a side's label is a locator. Both are kept.
        }
        blocks.append((block, slots))

    result: Translation = await translate(collect.lines, ENGLISH, language, sensitivity=sensitivity)
    # Every figure must survive, as on evidence (`language.evidence.checked`): a line that lost one
    # carries the English's figures.
    out = [
        checked(source, line)[0] for source, line in zip(collect.lines, result.lines, strict=True)
    ]

    def rebuilt(block: Block, slots: dict[str, object]) -> Block:
        items = slots["items"]
        columns = slots["columns"]
        rows = slots["rows"]
        block_facts = slots["facts"]
        assert isinstance(items, list) and isinstance(columns, list)
        assert isinstance(rows, list) and isinstance(block_facts, list)
        text_slots = slots["text"]
        assert isinstance(text_slots, list)
        return block.model_copy(
            update={
                "text": _put(block.text, text_slots, out),
                "items": [_put(i, s, out) for i, s in zip(block.items, items, strict=True)],
                "columns": [_put(c, s, out) for c, s in zip(block.columns, columns, strict=True)],
                "rows": [
                    [
                        Cell(text=_put(c.text, s, out), tone=c.tone)
                        for c, s in zip(row, row_slots, strict=True)
                    ]
                    for row, row_slots in zip(block.rows, rows, strict=True)
                ],
                "facts": [
                    (_put(k, ks, out), _put(v, vs, out))
                    for (k, v), (ks, vs) in zip(block.facts, block_facts, strict=True)
                ],
            }
        )

    banner = Block(
        kind="paragraph",
        tone="muted",
        text=(
            f"{language.name} ({language.native}): machine translation of the verified English "
            f"report by {result.engine} {result.engine_version}"
            + (" (fallback)" if result.fallback else "")
            + ". The English report is the master. Quotes from the evidence are kept as written."
        ),
    )
    return document.model_copy(
        update={
            "title": _put(document.title, title, out),
            "subtitle": _put(document.subtitle, subtitle, out),
            "facts": [
                (_put(k, ks, out), _put(v, vs, out))
                for (k, v), (ks, vs) in zip(document.facts, facts, strict=True)
            ],
            "blocks": [banner, *(rebuilt(b, s) for b, s in blocks)],
            "footer": f"{document.footer} · {language.code} · {result.engine}",
        }
    )
