"""The `ContextProvider` seam.

Member 2 owns the M2Context service. Member 1 owns this contract and a working local
implementation, so the retrieval story holds whether or not the remote service arrives — and
if it does, it swaps in here without touching any engine.

Selection is by environment variable. The remote adapter has a timeout and degrades to
local, recording that it did so. Silent degradation would leave a run looking like it
searched a corpus it never reached.
"""

from __future__ import annotations

import hashlib
from collections.abc import Sequence
from typing import Protocol, runtime_checkable

from app.core.config import ProviderMode, get_settings
from app.core.logging import get_logger
from app.intelligence.context.manager import (
    LocalContextProvider,
    RetrievedChunk,
    cosine_similarity,
)
from app.intelligence.context.store import (
    ContextStore,
    Ingested,
    MemoryContextStore,
    StoredDocument,
    chunk_text,
)
from app.llm.provider import LLMProvider

log = get_logger(__name__)

# Chunks per embedding call: the batch Member 2's ingest used, and the embedding config's.
EMBED_BATCH = 32


@runtime_checkable
class ContextProvider(Protocol):
    """Semantic retrieval over the run's accumulated context."""

    async def ingest(self, documents: dict[str, str]) -> int: ...

    async def retrieve(
        self, query: str, *, k: int = 5, scope: list[str] | None = None
    ) -> list[RetrievedChunk]: ...


def build_context_provider(llm: LLMProvider) -> ContextProvider:
    """The configured provider.

    `CONTEXT_PROVIDER=remote` will select the M2Context adapter once that service exists.
    Until then the local implementation is returned and the intent is logged, rather than
    failing a run over a service that was never deployed.
    """
    settings = get_settings()
    if settings.context_provider is ProviderMode.REMOTE:
        if not settings.m2context_base_url:
            log.warning(
                "context_provider_remote_unconfigured",
                reason="M2CONTEXT_BASE_URL is empty; using the local provider",
            )
        else:
            log.info("context_provider_remote_pending", url=settings.m2context_base_url)
    return LocalContextProvider(llm)


# --- Stored, workspace-scoped retrieval (Phase 40) ---------------------------------------------

_memory_store = MemoryContextStore()
# Probed once, like run persistence: a connection per search would be a round trip per query. Unit
# tests set it False so they never write to a developer's Postgres (tests/conftest.py).
_database: bool | None = None


def reset_context_store_probe() -> None:
    global _database
    _database = None


async def get_context_store() -> ContextStore:
    """pgvector when the database answers, the in-memory store otherwise.

    Unlike semantic memory (chosen by configuration, never by availability), retrieval may fall
    back: every answer names the store that gave it, and a passage found in memory is still a
    line of a document the run holds, so nothing durable is split across two stores.
    """
    global _database
    if _database is None:
        from app.database.session import database_available

        _database = await database_available()
    if _database:
        from app.database.context_store import PgVectorContextStore

        return PgVectorContextStore()
    return _memory_store


async def ingest_document(
    store: ContextStore,
    llm: LLMProvider,
    *,
    workspace_id: str,
    document_id: str,
    text: str,
    kind: str = "text",
    parser: str = "",
) -> Ingested:
    """Chunk, embed and store one document. A file whose SHA-256 is unchanged is skipped."""
    digest = hashlib.sha256(text.encode("utf-8")).hexdigest()
    existing = await store.current(workspace_id, document_id)
    if existing is not None and existing.sha256 == digest and existing.chunks:
        return Ingested(
            workspace_id=workspace_id,
            document_id=document_id,
            chunks=existing.chunks,
            unchanged=True,
            store=store.name,
        )

    chunks = chunk_text(document_id, text, get_settings().context_chunker)
    for start in range(0, len(chunks), EMBED_BATCH):
        batch = chunks[start : start + EMBED_BATCH]
        response = await llm.embed([c.text for c in batch])
        for chunk, vector in zip(batch, response.vectors, strict=False):
            chunk.embedding = vector
    embedded = [c for c in chunks if c.embedding]
    await store.replace(
        StoredDocument(
            workspace_id=workspace_id,
            document_id=document_id,
            kind=kind,
            sha256=digest,
            parser=parser,
        ),
        embedded,
    )
    log.info(
        "context_document_ingested",
        workspace=workspace_id,
        document=document_id,
        chunks=len(embedded),
        store=store.name,
    )
    return Ingested(
        workspace_id=workspace_id, document_id=document_id, chunks=len(embedded), store=store.name
    )


async def search_store(
    store: ContextStore,
    llm: LLMProvider,
    *,
    workspace_id: str,
    query: str,
    k: int = 5,
    document_ids: list[str] | None = None,
    min_score: float = 0.0,
) -> list[RetrievedChunk]:
    """The passages of a workspace closest in meaning to the query, best first.

    Each passage is cited at its line closest in meaning to the query, not at its first line.
    Measured on the Aurora reports: the first line of a matching chunk was usually its heading
    ("2. CURRENT STATUS"), and a citation the evidence binder resolves to a heading supports
    nothing. The chunk's text is kept as the passage, for context.
    """
    if not query.strip():
        return []
    response = await llm.embed([query])
    if not response.vectors:
        return []
    query_vector = response.vectors[0]
    hits = await store.search(workspace_id, query_vector, limit=k, document_ids=document_ids)
    return await _pinpoint(llm, query_vector, [h for h in hits if h.score >= min_score])


async def _pinpoint(
    llm: LLMProvider, query_vector: list[float], hits: list[RetrievedChunk]
) -> list[RetrievedChunk]:
    """Move each hit's citation to its line most similar to the query: one embedding call."""
    lines = [
        (index, offset, line)
        for index, hit in enumerate(hits)
        for offset, line in enumerate(hit.chunk.text.splitlines())
        if line.strip()
    ]
    if len(lines) <= len(hits):
        return hits  # one line per chunk: nothing to choose between
    response = await llm.embed([line for _, _, line in lines])
    best: dict[int, tuple[float, int]] = {}
    for (index, offset, _), vector in zip(lines, response.vectors, strict=False):
        score = cosine_similarity(query_vector, vector)
        if index not in best or score > best[index][0]:
            best[index] = (score, offset)
    pinned = []
    for index, hit in enumerate(hits):
        offset = best.get(index, (0.0, 0))[1]
        if offset and hit.chunk.locator.row is not None:
            locator = hit.chunk.locator.model_copy(update={"row": hit.chunk.locator.row + offset})
            chunk = hit.chunk.model_copy(update={"locator": locator})
            hit = hit.model_copy(update={"chunk": chunk})
        pinned.append(hit)
    return pinned


class StoreContextProvider:
    """`ContextProvider` over a workspace in the context store: what a mission's tool searches."""

    def __init__(self, llm: LLMProvider, store: ContextStore, workspace_id: str) -> None:
        self._llm = llm
        self._store = store
        self.workspace_id = workspace_id

    @property
    def name(self) -> str:
        return self._store.name

    async def ingest(self, documents: dict[str, str]) -> int:
        total = 0
        for document_id, text in documents.items():
            done = await ingest_document(
                self._store,
                self._llm,
                workspace_id=self.workspace_id,
                document_id=document_id,
                text=text,
            )
            total += done.chunks
        return total

    async def retrieve(
        self, query: str, *, k: int = 5, scope: list[str] | None = None
    ) -> list[RetrievedChunk]:
        return await search_store(
            self._store,
            self._llm,
            workspace_id=self.workspace_id,
            query=query,
            k=k,
            document_ids=scope,
        )


async def workspace_retriever(
    workspace_id: str,
    documents: dict[str, str],
    loaded: Sequence[object],
    llm: LLMProvider,
) -> StoreContextProvider | None:
    """Ingest a mission's documents into its workspace and return the retriever over them.

    None when the store or the embedding model fails: the mission still runs, with lexical recall,
    and the log says why. Never failing a run over retrieval is the same rule as persistence.
    """
    kinds = {getattr(d, "document_id", ""): d for d in loaded}
    try:
        store = await get_context_store()
        for document_id, text in documents.items():
            source = kinds.get(document_id)
            await ingest_document(
                store,
                llm,
                workspace_id=workspace_id,
                document_id=document_id,
                text=text,
                kind=str(getattr(source, "kind", "text")),
                parser=str(getattr(source, "parser", "")),
            )
    except Exception as exc:  # noqa: BLE001 - retrieval is optional, never fatal
        log.warning(
            "workspace_ingest_failed", workspace=workspace_id, error=f"{type(exc).__name__}: {exc}"
        )
        return None
    return StoreContextProvider(llm, store, workspace_id)
