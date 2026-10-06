"""Stored, workspace-scoped retrieval (Phase 40): Member 2's ingest and search, over HTTP.

A workspace is a named set of documents whose passages are chunked, embedded and stored, so they
can be searched by meaning. Uploads go to the `default` workspace unless another is named; a
mission that names a workspace has its documents ingested there and searches them.

Every answer names the store that gave it (`pgvector`, or `memory` when the database is down) and
every passage is a citation (`report.txt:r12`), so a hit can start an investigation of that file.
"""

from __future__ import annotations

from fastapi import APIRouter, status
from pydantic import Field

from app.api.errors import ApiError
from app.api.v1.documents import indexing_now
from app.integrations.context import get_context_store, ingest_document, search_store
from app.intelligence.context.store import (
    DEFAULT_WORKSPACE,
    MAX_RESULTS,
    Ingested,
    RetrievalHit,
    StoredDocument,
)
from app.llm import get_provider
from app.schemas.common import JarvisModel
from app.tools.formats import prepare
from app.tools.loader import load_by_name, resolve_document

router = APIRouter(prefix="/context", tags=["context"])

WORKSPACE = r"^[A-Za-z0-9_-]{1,64}$"


class IngestRequest(JarvisModel):
    workspace_id: str = Field(default=DEFAULT_WORKSPACE, pattern=WORKSPACE)
    documents: list[str] = Field(min_length=1, max_length=64)


class IngestResponse(JarvisModel):
    store: str
    ingested: list[Ingested] = Field(default_factory=list)
    # Named but not readable (missing, or no text yet): reported, not silently dropped.
    skipped: list[str] = Field(default_factory=list)


class RetrieveRequest(JarvisModel):
    workspace_id: str = Field(default=DEFAULT_WORKSPACE, pattern=WORKSPACE)
    query: str = Field(min_length=1, max_length=2000)
    k: int = Field(default=5, ge=1, le=MAX_RESULTS)
    # Passages scoring below this are dropped. Cosine similarity mapped to [0, 1]. Default 0 by
    # measurement (Experiment 006): non-answers scored up to 0.80 with nomic-embed-text, above many
    # real answers, so no threshold separates them.
    min_score: float = Field(default=0.0, ge=0.0, le=1.0)
    documents: list[str] = Field(default_factory=list, max_length=64)


class RetrieveResponse(JarvisModel):
    store: str
    workspace_id: str
    hits: list[RetrievalHit] = Field(default_factory=list)


class Workspace(JarvisModel):
    workspace_id: str
    documents: list[StoredDocument] = Field(default_factory=list)
    store: str
    # Uploads still being indexed in the background (any workspace): listed so a person knows
    # why a file they just added is not searchable yet.
    indexing: list[str] = Field(default_factory=list)


@router.post("/ingest", response_model=IngestResponse)
async def ingest(body: IngestRequest) -> IngestResponse:
    """Chunk, embed and store documents in a workspace. Unchanged files are not re-embedded."""
    llm = get_provider()
    await prepare([resolve_document(n) for n in body.documents], llm)
    documents, loaded = load_by_name(body.documents)
    by_id = {d.document_id: d for d in loaded}
    store = await get_context_store()
    done = []
    try:
        for document_id, text in documents.items():
            source = by_id.get(document_id)
            done.append(
                await ingest_document(
                    store,
                    llm,
                    workspace_id=body.workspace_id,
                    document_id=document_id,
                    text=text,
                    kind=str(source.kind) if source else "text",
                    parser=source.parser if source else "",
                )
            )
    except Exception as exc:
        raise ApiError(
            "CONTEXT_UNAVAILABLE",
            f"could not embed or store the documents: {type(exc).__name__}: {exc}",
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        ) from exc
    return IngestResponse(
        store=store.name,
        ingested=done,
        skipped=[n for n in body.documents if n not in documents],
    )


@router.post("/retrieve", response_model=RetrieveResponse)
async def retrieve(body: RetrieveRequest) -> RetrieveResponse:
    """The workspace's passages closest in meaning to the query, each a citation."""
    store = await get_context_store()
    try:
        found = await search_store(
            store,
            get_provider(),
            workspace_id=body.workspace_id,
            query=body.query,
            k=body.k,
            document_ids=body.documents or None,
            min_score=body.min_score,
        )
    except Exception as exc:
        raise ApiError(
            "CONTEXT_UNAVAILABLE",
            f"could not search the workspace: {type(exc).__name__}: {exc}",
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        ) from exc
    return RetrieveResponse(
        store=store.name,
        workspace_id=body.workspace_id,
        hits=[
            RetrievalHit(
                source=h.chunk.source,
                document_id=h.chunk.locator.document_id,
                line=h.chunk.locator.row,
                text=h.chunk.text,
                score=round(h.score, 4),
            )
            for h in found
        ],
    )


@router.get("/workspaces", response_model=list[str])
async def workspaces() -> list[str]:
    """Every workspace that holds a document, and `default` always."""
    return await (await get_context_store()).workspaces()


@router.get("/workspaces/{workspace_id}", response_model=Workspace)
async def workspace(workspace_id: str) -> Workspace:
    """A workspace's documents, with their parser, hash and chunk count."""
    store = await get_context_store()
    return Workspace(
        workspace_id=workspace_id,
        documents=await store.documents(workspace_id),
        store=store.name,
        indexing=indexing_now(),
    )
