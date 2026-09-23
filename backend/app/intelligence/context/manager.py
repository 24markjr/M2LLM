"""Context management and semantic retrieval.

Two jobs, both in service of the same constraint: the agent accumulates more than fits in a
prompt, and what it drops determines what it can later prove.

**Retrieval** finds passages by meaning rather than keyword. `DocumentSearchTool` matches
words; a query for "budget overrun" will not find "spend exceeds the approved figure". Real
embeddings close that gap.

**Compaction** shrinks accumulated observations when they outgrow the budget — and the rule
that makes it safe is that **source locators are never compacted away**. A summary that
loses its sources cannot support a finding, so the evidence binder would mark every claim
built on it UNRESOLVED. Compaction may lose prose. It may not lose provenance.

Retrieval sits behind `ContextProvider`, so Member 2's M2Context service swaps in at one
seam (`app/integrations/`) without touching anything here.
"""

from __future__ import annotations

import math

from pydantic import Field

from app.core.logging import get_logger
from app.llm.provider import LLMProvider
from app.schemas.common import JarvisModel, NonEmptyStr, SourceLocator, UnitFloat
from app.schemas.execution import Observation

log = get_logger(__name__)


class Chunk(JarvisModel):
    """One retrievable passage, with the locator that makes it citable."""

    chunk_id: str
    locator: SourceLocator
    text: NonEmptyStr
    embedding: list[float] = Field(default_factory=list, exclude=True)

    @property
    def source(self) -> str:
        return self.locator.as_ref()


class RetrievedChunk(JarvisModel):
    chunk: Chunk
    score: UnitFloat


def cosine_similarity(a: list[float], b: list[float]) -> float:
    """Similarity of two embedding vectors, normalised into [0, 1].

    Mapped from [-1, 1] so it can be used directly as a relevance score without a caller
    having to remember the convention.
    """
    if not a or not b or len(a) != len(b):
        return 0.0
    dot = sum(x * y for x, y in zip(a, b, strict=True))
    norm_a = math.sqrt(sum(x * x for x in a))
    norm_b = math.sqrt(sum(y * y for y in b))
    if norm_a == 0.0 or norm_b == 0.0:
        return 0.0
    return max(0.0, min(1.0, (dot / (norm_a * norm_b) + 1.0) / 2.0))


def chunk_document(document_id: str, text: str, *, max_lines: int = 4) -> list[Chunk]:
    """Split a document into passages, keeping the line number of each passage's start.

    Line-level locators are what let a retrieved passage become citable evidence. Chunking
    that loses them would produce text the binder cannot resolve.
    """
    lines = text.splitlines()
    chunks: list[Chunk] = []
    buffer: list[str] = []
    start = 1

    def flush(end_line: int) -> None:
        body = "\n".join(buffer).strip()
        if body:
            chunks.append(
                Chunk(
                    chunk_id=f"{document_id}:{start}",
                    locator=SourceLocator(
                        document_id=document_id, document_name=document_id, row=start
                    ),
                    text=body,
                )
            )

    for number, line in enumerate(lines, start=1):
        if not buffer:
            start = number
        buffer.append(line)
        if len(buffer) >= max_lines or not line.strip():
            flush(number)
            buffer = []

    if buffer:
        flush(len(lines))
    return chunks


class LocalContextProvider:
    """In-memory semantic retrieval over the run's documents.

    The default implementation behind `ContextProvider`. Embeddings come from the configured
    model, so the matching is genuinely semantic rather than lexical.

    Held in memory rather than pgvector for now: the persistence layer is Phase 3, still
    blocked on a local Docker install. The interface is the same either way, which is the
    point of the seam - moving to pgvector changes this class and nothing that calls it.
    """

    def __init__(self, provider: LLMProvider) -> None:
        self._provider = provider
        self._chunks: list[Chunk] = []

    @property
    def chunk_count(self) -> int:
        return len(self._chunks)

    async def ingest(self, documents: dict[str, str]) -> int:
        """Chunk and embed a set of documents. Returns the number of chunks indexed."""
        chunks: list[Chunk] = []
        for document_id, text in documents.items():
            chunks.extend(chunk_document(document_id, text))

        if not chunks:
            return 0

        response = await self._provider.embed([c.text for c in chunks])
        for chunk, vector in zip(chunks, response.vectors, strict=False):
            chunk.embedding = vector

        self._chunks = [c for c in chunks if c.embedding]
        log.info("context_ingested", documents=len(documents), chunks=len(self._chunks))
        return len(self._chunks)

    async def retrieve(
        self, query: str, *, k: int = 5, scope: list[str] | None = None
    ) -> list[RetrievedChunk]:
        """Find the passages most similar in meaning to the query."""
        if not self._chunks or not query.strip():
            return []

        candidates = [c for c in self._chunks if not scope or c.locator.document_id in scope]
        if not candidates:
            return []

        response = await self._provider.embed([query])
        if not response.vectors:
            return []
        query_vector = response.vectors[0]

        scored = [
            RetrievedChunk(chunk=c, score=cosine_similarity(query_vector, c.embedding))
            for c in candidates
        ]
        scored.sort(key=lambda r: r.score, reverse=True)
        return scored[:k]


class ContextManager:
    """The run's working memory.

    Holds accumulated observations and hands each component only what it needs. A component
    given the whole state tends to use the whole state, which is how a verifier ends up
    seeing the reasoning it was supposed to check independently.
    """

    def __init__(self, provider: LocalContextProvider | None = None) -> None:
        self.observations: list[Observation] = []
        self.retrieval = provider

    def record(self, observation: Observation) -> None:
        self.observations.append(observation)

    @property
    def all_sources(self) -> set[str]:
        return {s for o in self.observations for s in o.sources}

    def snapshot_for_reasoning(self, *, token_budget: int = 6000) -> list[Observation]:
        """Observations for the reasoning engine, compacted if they exceed the budget."""
        return compact(self.observations, token_budget=token_budget)

    def snapshot_for_verification(
        self, claim: str, evidence_text: dict[str, str]
    ) -> dict[str, str]:
        """Deliberately minimal: the claim and its evidence, nothing else.

        There is no parameter here for the reasoning trail, and that absence is the contract
        (Phase 15). A verifier shown the argument tends to be persuaded by it.
        """
        return {"claim": claim, **evidence_text}


def estimate_tokens(observations: list[Observation]) -> int:
    """Rough token count. Four characters per token is close enough to size a budget."""
    return sum(len(o.content) + len(str(o.structured)) for o in observations) // 4


def compact(observations: list[Observation], *, token_budget: int = 6000) -> list[Observation]:
    """Shrink observations to fit a budget, preserving every source locator.

    Oldest first, because recent observations are usually what the current reasoning step is
    about. Structured payloads are dropped and content is summarised - but `sources` is
    carried through untouched. Losing a locator would make every claim built on that
    observation unresolvable, which is a far worse outcome than a longer prompt.
    """
    if estimate_tokens(observations) <= token_budget:
        return list(observations)

    compacted: list[Observation] = []
    for observation in observations:
        compacted.append(
            observation.model_copy(
                update={
                    "content": _summarise(observation),
                    "structured": {},
                    "compacted": True,
                }
            )
        )
        if estimate_tokens(compacted + observations[len(compacted) :]) <= token_budget:
            return compacted + observations[len(compacted) :]

    return compacted


def _summarise(observation: Observation) -> str:
    return f"{observation.task_type}: {observation.content} ({len(observation.sources)} source(s))"
