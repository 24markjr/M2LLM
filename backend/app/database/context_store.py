"""The pgvector context store (Phase 40): chunks and vectors in Postgres, by workspace.

The `documents` and `document_chunks` tables have existed since Phase 3 (ADR-005: pgvector beside
the findings, so a passage an evidence item points at is a join away). Until Phase 40 nothing wrote
to them. Similarity is the database's cosine distance, mapped to [0, 1] exactly as the in-memory
store maps cosine similarity, so the two stores score alike.
"""

from __future__ import annotations

from sqlalchemy import delete, func, select

from app.database.session import session_scope
from app.intelligence.context.manager import Chunk, RetrievedChunk
from app.intelligence.context.store import DEFAULT_WORKSPACE, MAX_RESULTS, StoredDocument
from app.models.tables import Document, DocumentChunk
from app.schemas.common import SourceLocator


class PgVectorContextStore:
    name = "pgvector"

    async def current(self, workspace_id: str, document_id: str) -> StoredDocument | None:
        async with session_scope() as session:
            row = (
                await session.execute(
                    select(Document).where(
                        Document.workspace_id == workspace_id, Document.document_id == document_id
                    )
                )
            ).scalar_one_or_none()
            if row is None:
                return None
            count = (
                await session.execute(
                    select(func.count())
                    .select_from(DocumentChunk)
                    .where(DocumentChunk.document_pk == row.id)
                )
            ).scalar_one()
            return _stored(row, int(count))

    async def replace(self, document: StoredDocument, chunks: list[Chunk]) -> None:
        async with session_scope() as session:
            await session.execute(
                delete(Document).where(
                    Document.workspace_id == document.workspace_id,
                    Document.document_id == document.document_id,
                )
            )
            await session.flush()
            row = Document(
                workspace_id=document.workspace_id,
                document_id=document.document_id,
                name=document.document_id,
                kind=document.kind,
                sha256=document.sha256,
                parser=document.parser,
                line_count=0,
            )
            session.add(row)
            await session.flush()
            session.add_all(
                DocumentChunk(
                    document_pk=row.id,
                    chunk_id=chunk.chunk_id,
                    locator=chunk.source,
                    page=chunk.locator.page,
                    row=chunk.locator.row,
                    text=chunk.text,
                    embedding=chunk.embedding or None,
                )
                for chunk in chunks
            )

    async def search(
        self,
        workspace_id: str,
        vector: list[float],
        *,
        limit: int,
        document_ids: list[str] | None = None,
    ) -> list[RetrievedChunk]:
        distance = DocumentChunk.embedding.cosine_distance(vector)
        query = (
            select(DocumentChunk, Document.document_id, distance.label("distance"))
            .join(Document, DocumentChunk.document_pk == Document.id)
            .where(Document.workspace_id == workspace_id, DocumentChunk.embedding.is_not(None))
        )
        if document_ids:
            query = query.where(Document.document_id.in_(document_ids))
        query = query.order_by(distance, DocumentChunk.chunk_id).limit(
            max(1, min(limit, MAX_RESULTS))
        )
        async with session_scope() as session:
            rows = (await session.execute(query)).all()
        hits = []
        for chunk_row, document_id, dist in rows:
            chunk = Chunk(
                chunk_id=chunk_row.chunk_id,
                locator=SourceLocator(
                    document_id=document_id,
                    document_name=document_id,
                    row=chunk_row.row,
                    page=chunk_row.page,
                ),
                text=chunk_row.text,
            )
            # Cosine distance is 1 - cos, in [0, 2]; the in-memory store scores (cos + 1) / 2.
            hits.append(
                RetrievedChunk(chunk=chunk, score=max(0.0, min(1.0, 1.0 - float(dist) / 2.0)))
            )
        return hits

    async def documents(self, workspace_id: str) -> list[StoredDocument]:
        async with session_scope() as session:
            rows = (
                await session.execute(
                    select(Document, func.count(DocumentChunk.id))
                    .outerjoin(DocumentChunk, DocumentChunk.document_pk == Document.id)
                    .where(Document.workspace_id == workspace_id)
                    .group_by(Document.id)
                    .order_by(Document.document_id)
                )
            ).all()
        return [_stored(row, int(count)) for row, count in rows]

    async def workspaces(self) -> list[str]:
        async with session_scope() as session:
            names = (await session.execute(select(Document.workspace_id).distinct())).scalars()
            return sorted(set(names) | {DEFAULT_WORKSPACE})


def _stored(row: Document, chunks: int) -> StoredDocument:
    return StoredDocument(
        workspace_id=row.workspace_id,
        document_id=row.document_id,
        kind=row.kind,
        sha256=row.sha256,
        parser=row.parser,
        chunks=chunks,
    )
