"""Stored, workspace-scoped retrieval (Phase 40, Member 2's ingest and search).

Member 2's M2LLM chunked documents (600 characters, 80 overlapping), embedded each chunk, stored the
vectors in Qdrant with an in-memory fallback, and searched within a workspace. This is that design
on this codebase's stores (decision D9: pgvector, ADR-005) and models (D10: the embedding model
Ollama serves, `nomic-embed-text`):

- **Chunks keep their starting line**, whichever chunker made them, so a retrieved passage is a
  citation (`report.txt:r12`) the evidence binder can resolve - not free text.
- **One protocol, two stores**: pgvector when the database is up, memory otherwise - Member 2's
  Qdrant-with-fallback, said out loud: every search result names the store that answered.
- **Ingest is idempotent per file**: a document whose SHA-256 is unchanged is not re-embedded.

Their chunker and ours both exist; which is the default is decided by measurement (Experiment
006, Phase 41), as every default since Phase 34.
"""

from __future__ import annotations

from typing import Protocol

from pydantic import Field

from app.intelligence.context.manager import (
    Chunk,
    RetrievedChunk,
    chunk_document,
    cosine_similarity,
)
from app.schemas.common import JarvisModel, SourceLocator

# Member 2's chunker: characters per chunk, and how many the next chunk repeats.
CHUNK_CHARS = 600
CHUNK_OVERLAP = 80
DEFAULT_WORKSPACE = "default"
MAX_RESULTS = 50


class StoredDocument(JarvisModel):
    """A document as a workspace holds it."""

    workspace_id: str
    document_id: str
    kind: str = "text"
    sha256: str = ""
    parser: str = ""
    # The chunker that cut it (Phase 41), so a change of chunker is not mistaken for "unchanged".
    chunker: str = "lines"
    chunks: int = 0


def chunk_by_chars(
    document_id: str, text: str, *, size: int = CHUNK_CHARS, overlap: int = CHUNK_OVERLAP
) -> list[Chunk]:
    """Member 2's chunker: fixed-size windows of characters, overlapping.

    Each chunk records the line its first character is on, so it is as citable as a line chunk.
    Windows start at the beginning of a word where they can, so a chunk does not open mid-word.
    """
    if size <= overlap:
        raise ValueError("chunk size must exceed the overlap")
    chunks: list[Chunk] = []
    start = 0
    while start < len(text):
        if start and not text[start - 1].isspace():
            nudge = text.find(" ", start, min(len(text), start + 40))
            if nudge != -1:
                start = nudge + 1
        window = text[start : start + size]
        body = window.strip()
        if body:
            # The line of the first character kept, so line i of the chunk is document line row + i.
            lead = len(window) - len(window.lstrip())
            line = text.count("\n", 0, start + lead) + 1
            chunks.append(
                Chunk(
                    chunk_id=f"{document_id}:c{start}",
                    locator=SourceLocator(
                        document_id=document_id, document_name=document_id, row=line
                    ),
                    text=body,
                )
            )
        if start + size >= len(text):
            break
        start += size - overlap
    return chunks


def chunk_text(document_id: str, text: str, chunker: str) -> list[Chunk]:
    """Chunks by the configured strategy: `lines` (ours) or `chars` (Member 2's 600/80)."""
    if chunker == "chars":
        return chunk_by_chars(document_id, text)
    return chunk_document(document_id, text)


class ContextStore(Protocol):
    """Where chunks and their vectors live, by workspace."""

    name: str

    async def current(self, workspace_id: str, document_id: str) -> StoredDocument | None: ...

    async def replace(self, document: StoredDocument, chunks: list[Chunk]) -> None:
        """Store a document's chunks (with embeddings), replacing any earlier copy."""
        ...

    async def search(
        self,
        workspace_id: str,
        vector: list[float],
        *,
        limit: int,
        document_ids: list[str] | None = None,
    ) -> list[RetrievedChunk]: ...

    async def documents(self, workspace_id: str) -> list[StoredDocument]: ...

    async def workspaces(self) -> list[str]: ...


class MemoryContextStore:
    """The fallback when there is no database. Lost on restart, and says so by its name."""

    name = "memory"

    def __init__(self) -> None:
        self._documents: dict[tuple[str, str], StoredDocument] = {}
        self._chunks: dict[tuple[str, str], list[Chunk]] = {}

    async def current(self, workspace_id: str, document_id: str) -> StoredDocument | None:
        return self._documents.get((workspace_id, document_id))

    async def replace(self, document: StoredDocument, chunks: list[Chunk]) -> None:
        key = (document.workspace_id, document.document_id)
        self._documents[key] = document.model_copy(update={"chunks": len(chunks)})
        self._chunks[key] = list(chunks)

    async def search(
        self,
        workspace_id: str,
        vector: list[float],
        *,
        limit: int,
        document_ids: list[str] | None = None,
    ) -> list[RetrievedChunk]:
        scored = [
            RetrievedChunk(chunk=chunk, score=cosine_similarity(vector, chunk.embedding))
            for (workspace, document_id), chunks in self._chunks.items()
            if workspace == workspace_id and (not document_ids or document_id in document_ids)
            for chunk in chunks
            if chunk.embedding
        ]
        scored.sort(key=lambda r: (-r.score, r.chunk.chunk_id))
        return scored[: max(1, min(limit, MAX_RESULTS))]

    async def documents(self, workspace_id: str) -> list[StoredDocument]:
        return sorted(
            (d for (w, _), d in self._documents.items() if w == workspace_id),
            key=lambda d: d.document_id,
        )

    async def workspaces(self) -> list[str]:
        return sorted({w for w, _ in self._documents} | {DEFAULT_WORKSPACE})


class Ingested(JarvisModel):
    workspace_id: str
    document_id: str
    chunks: int = 0
    # Unchanged since the last ingest (same SHA-256): nothing was re-embedded.
    unchanged: bool = False
    store: str = ""


class RetrievalHit(JarvisModel):
    """One passage, citable, with the score that ranked it."""

    source: str
    document_id: str
    line: int | None = None
    text: str
    score: float = Field(ge=0.0, le=1.0)


# Reciprocal rank fusion's constant: the usual 60, which keeps one list's top rank from drowning
# the other list's.
RRF_K = 60


def fuse(
    rankings: list[list[tuple[str, int]]], *, k: int = RRF_K
) -> list[tuple[tuple[str, int], float]]:
    """Reciprocal rank fusion of several rankings of (document, line) citations, best first.

    Phase 41 (Experiment 006): word matching won keyword queries and embeddings won paraphrases,
    so a citation ranked well by either should rank well. Ranks are fused, not scores: the two
    searches score on unrelated scales.
    """
    fused: dict[tuple[str, int], float] = {}
    for ranking in rankings:
        for rank, key in enumerate(dict.fromkeys(ranking), start=1):
            fused[key] = fused.get(key, 0.0) + 1.0 / (k + rank)
    return sorted(fused.items(), key=lambda item: (-item[1], item[0]))
