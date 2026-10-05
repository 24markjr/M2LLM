"""Knowledge extraction: documents in, a run's knowledge base out (K1, plus A6-A8).

Ported from Member 3's `extractor.py`, which sent each text chunk to Ollama (`qwen2.5:7b`, via
`requests`) asking for entities, relationships and claims as JSON, and returned empty lists if the
answer was not valid JSON. The same three outputs are extracted here, with four changes:

1. **The model is reached through `LLMProvider`** (invariant 1), with a versioned prompt
   (`.agent/prompts/knowledge.md`) and schema-constrained output with repair. A chunk that still
   fails is counted (`failed_chunks`), never silently empty.
2. **Every claim is grounded (A6).** Lines go to the model numbered, and it returns a line per
   item. A claim's value must appear on its line (text, an equal date, or an equal figure). If it
   is not there, the other lines of the chunk are searched. A value found nowhere is kept with
   `grounded=False`: shown, counted, and never used to detect a conflict. A model that wrote a value
   rather than read it cannot create a contradiction.
3. **CSV files need no model (A7).** The first mostly-non-numeric column names the entity and every
   other cell is a claim at its exact row. Deterministic, and exact to the line.
4. **Names carry across chunks (A8).** Entity and attribute names already used in the run are
   given to the next chunk's prompt. The original's biggest recall limit was the same fact
   extracted under two attribute names in two documents, which can never conflict.

Bounded (invariant 7): at most `knowledge.max_chunks` model calls per run. Chunks past it are
counted as `chunks_skipped`, so a knowledge base built from part of the input never looks complete.
"""

from __future__ import annotations

import csv
import re
from dataclasses import dataclass

from pydantic import Field

from app.core.agent_config import KnowledgePolicy, get_knowledge_policy
from app.core.logging import get_logger
from app.intelligence.knowledge.conflicts import detect_conflicts
from app.intelligence.knowledge.store import KnowledgeAccumulator, normalize_name
from app.intelligence.temporal import find_dates, find_figures, parse_date, parse_number
from app.llm.errors import LLMError
from app.llm.prompts import get_prompt_library
from app.llm.provider import LLMProvider
from app.llm.structured import generate_structured
from app.schemas.common import JarvisModel
from app.schemas.evidence import is_seen_line
from app.schemas.knowledge import KnowledgeSnapshot
from app.security.injection import wrap_untrusted
from app.tools.loader import MAX_CSV_ROWS, source_ref

log = get_logger(__name__)

_PAGE_MARKER = re.compile(r"^--- page \d+ ---$")


# --- what the model returns ------------------------------------------------------


class ExtractedEntity(JarvisModel):
    name: str = ""
    type: str = "OTHER"


class ExtractedRelationship(JarvisModel):
    subject: str = ""
    predicate: str = ""
    object: str = ""
    line: int | None = None


class ExtractedClaim(JarvisModel):
    entity: str = ""
    attribute: str = ""
    value: str = ""
    line: int | None = None


class ExtractionResponse(JarvisModel):
    entities: list[ExtractedEntity] = Field(default_factory=list)
    relationships: list[ExtractedRelationship] = Field(default_factory=list)
    claims: list[ExtractedClaim] = Field(default_factory=list)


# --- chunks ------------------------------------------------------------------------


@dataclass(frozen=True)
class Chunk:
    """Consecutive non-blank lines of one document, with their 1-based line numbers."""

    document_id: str
    lines: tuple[tuple[int, str], ...]

    @property
    def first_line(self) -> int:
        return self.lines[0][0]

    def text_of(self, line: int) -> str:
        return next((text for number, text in self.lines if number == line), "")

    def contains(self, line: int | None) -> bool:
        return line is not None and any(number == line for number, _ in self.lines)

    def numbered(self) -> str:
        return "\n".join(f"{number}| {text}" for number, text in self.lines)


def chunk_document(document_id: str, text: str, chunk_chars: int) -> list[Chunk]:
    """Split a document into chunks of whole lines, at most `chunk_chars` characters each.

    Blank lines and PDF page markers are not content and are not sent. A single line longer
    than the limit becomes a chunk on its own rather than being cut.
    """
    chunks: list[Chunk] = []
    current: list[tuple[int, str]] = []
    size = 0
    for number, raw in enumerate(text.splitlines(), start=1):
        line = raw.strip()
        if not line or _PAGE_MARKER.match(line):
            continue
        if current and size + len(line) > chunk_chars:
            chunks.append(Chunk(document_id, tuple(current)))
            current, size = [], 0
        current.append((number, line))
        size += len(line) + 1
    if current:
        chunks.append(Chunk(document_id, tuple(current)))
    return chunks


# --- grounding (A6) ------------------------------------------------------------------


def _fold(text: str) -> str:
    return " ".join(text.casefold().split()).strip(" .,;:")


def value_on_line(value: str, line: str) -> bool:
    """Whether `line` states `value`: as text, as a compatible date, or as an equal figure."""
    folded = _fold(value)
    if folded and folded in _fold(line):
        return True
    date = parse_date(value)
    if date is not None and any(date.compatible(seen) for _, seen in find_dates(line)):
        return True
    number = parse_number(value)
    return number is not None and any(number == seen for _, seen in find_figures(line))


def ground(value: str, stated: int | None, chunk: Chunk) -> tuple[int, bool]:
    """The line a value is on, and whether it was found at all.

    The stated line first; then the rest of the chunk. Not found: the stated line if it is in the
    chunk, else the chunk's first line, with `grounded=False`.
    """
    # A line a vision model wrote (`[seen]`, Phase 39) is its account of an image, not source text,
    # so a value found only there is not grounded: shown, and never used to detect a conflict.
    if (
        chunk.contains(stated)
        and value_on_line(value, chunk.text_of(stated or 0))
        and not is_seen_line(chunk.text_of(stated or 0))
    ):
        return stated or chunk.first_line, True
    for number, text in chunk.lines:
        if value_on_line(value, text) and not is_seen_line(text):
            return number, True
    for number, text in chunk.lines:
        if value_on_line(value, text):
            return number, False
    return (stated if chunk.contains(stated) and stated else chunk.first_line), False


def _mention_lines(name: str, chunk: Chunk) -> list[int]:
    key = normalize_name(name)
    return [n for n, text in chunk.lines if key and key in normalize_name(text)]


# --- the extractor -------------------------------------------------------------------


class KnowledgeExtractor:
    """Builds one run's knowledge base. Nothing is kept between runs."""

    def __init__(self, provider: LLMProvider, policy: KnowledgePolicy | None = None) -> None:
        self._provider = provider
        self._policy = policy or get_knowledge_policy()
        self._prompts = get_prompt_library()

    async def build(
        self,
        documents: dict[str, str],
        page_starts: dict[str, list[int]] | None = None,
        *,
        emit: object | None = None,
    ) -> KnowledgeSnapshot:
        pages = page_starts or {}
        store = KnowledgeAccumulator(max_claims=self._policy.max_claims)
        store.stats.documents = len(documents)

        chunks: list[Chunk] = []
        for document_id, text in documents.items():
            if document_id.lower().endswith(".csv"):
                self._tabular(document_id, text, store, pages)
            else:
                chunks.extend(chunk_document(document_id, text, self._policy.chunk_chars))

        store.stats.chunks = len(chunks)
        sent = chunks[: self._policy.max_chunks]
        store.stats.chunks_skipped = len(chunks) - len(sent)
        if store.stats.chunks_skipped:
            log.warning(
                "knowledge_chunks_skipped",
                skipped=store.stats.chunks_skipped,
                ceiling=self._policy.max_chunks,
            )

        # Sequential on purpose: each chunk's prompt carries the names the previous ones used.
        for chunk in sent:
            await self._extract(chunk, store, pages, emit)

        snapshot = store.snapshot()
        return snapshot.model_copy(
            update={"conflicts": detect_conflicts(snapshot.claims, snapshot.entities)}
        )

    async def _extract(
        self,
        chunk: Chunk,
        store: KnowledgeAccumulator,
        pages: dict[str, list[int]],
        emit: object | None,
    ) -> None:
        limit = self._policy.max_known_terms
        prompt = self._prompts.get("knowledge").render(
            document=chunk.document_id,
            lines=wrap_untrusted(chunk.document_id, chunk.numbered()),
            known_entities=_listing(store.entity_names[:limit]),
            known_attributes=_listing(store.attribute_names[:limit]),
        )
        store.stats.llm_calls += 1
        try:
            response = await generate_structured(
                self._provider, ExtractionResponse, prompt, role="knowledge", emit=emit
            )
        except LLMError as exc:
            # A chunk the model could not extract from is counted, never silently empty.
            store.stats.failed_chunks += 1
            log.warning("knowledge_chunk_failed", document=chunk.document_id, error=str(exc))
            return

        def ref(line: int) -> str:
            return source_ref(chunk.document_id, line, pages)

        for entity in response.entities:
            mentioned = _mention_lines(entity.name, chunk)
            if not mentioned:
                # Grounding applies to names too: a name on no line was written, not read.
                store.stats.entities_ungrounded += 1
                continue
            for line in mentioned:
                store.entity(entity.name, entity.type, ref(line))

        for rel in response.relationships:
            if chunk.contains(rel.line):
                line = rel.line or chunk.first_line
            else:
                both = [
                    n
                    for n in _mention_lines(rel.subject, chunk)
                    if n in _mention_lines(rel.object, chunk)
                ]
                line = (both or _mention_lines(rel.object, chunk) or [chunk.first_line])[0]
            store.relationship(rel.subject, rel.predicate, rel.object, ref(line))

        for claim in response.claims:
            line, grounded = ground(claim.value, claim.line, chunk)
            store.claim(
                entity_name=claim.entity,
                attribute=claim.attribute,
                value=claim.value,
                source=ref(line),
                document_id=chunk.document_id,
                line=line,
                quote=chunk.text_of(line),
                grounded=grounded,
            )

    @staticmethod
    def _tabular(
        document_id: str, text: str, store: KnowledgeAccumulator, pages: dict[str, list[int]]
    ) -> None:
        """A CSV as claims, without a model: one entity per row, one claim per other cell (A7)."""
        lines = text.splitlines()
        if len(lines) < 2:
            return
        header = next(csv.reader([lines[0]]))
        rows = [
            (number, next(csv.reader([raw])))
            for number, raw in enumerate(lines[1 : 1 + MAX_CSV_ROWS], start=2)
            if raw.strip()
        ]

        # The entity column: the first whose values are mostly not numbers.
        entity_column = 0
        for index in range(len(header)):
            values = [row[index] for _, row in rows if index < len(row) and row[index].strip()]
            if values and sum(parse_number(v) is None for v in values) * 2 > len(values):
                entity_column = index
                break

        for number, row in rows:
            if entity_column >= len(row) or not row[entity_column].strip():
                continue
            name = row[entity_column].strip()
            source = source_ref(document_id, number, pages)
            store.entity(name, "OTHER", source)
            store.stats.tabular_rows += 1
            for index, column in enumerate(header):
                if index == entity_column or index >= len(row) or not row[index].strip():
                    continue
                store.claim(
                    entity_name=name,
                    attribute=column,
                    value=row[index],
                    source=source,
                    document_id=document_id,
                    line=number,
                    quote=lines[number - 1],
                    grounded=True,
                )


def _listing(names: list[str]) -> str:
    return "\n".join(f"- {name}" for name in names) if names else "(none yet)"
