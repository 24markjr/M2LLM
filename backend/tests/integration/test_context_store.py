"""Phase 40: the pgvector context store against a real Postgres, held to the memory store's checks.

One suite, both stores (the rule since ADR-010): the same documents give the same citations and
the same ranking from either. Each test uses its own workspace and deletes it afterwards.
"""

from __future__ import annotations

import asyncio
import uuid
from collections.abc import AsyncIterator

import pytest
from sqlalchemy import delete

from app.database.context_store import PgVectorContextStore
from app.database.session import database_available, dispose_engine, session_scope
from app.integrations.context import ingest_document, search_store
from app.intelligence.context.store import ContextStore, MemoryContextStore
from app.llm.echo import EchoProvider
from app.models.tables import Document

pytestmark = pytest.mark.integration

REPORT = """PROJECT HELIX - STATUS REPORT

The target completion date is 2026-04-30.
The approved budget is 380,000 for the migration phase.

Vendor availability remains the principal schedule risk.
"""
CHUNK_TWO = (
    "The target completion date is 2026-04-30.\n"
    "The approved budget is 380,000 for the migration phase."
)


def _db_available() -> bool:
    async def probe() -> bool:
        try:
            return await database_available()
        finally:
            await dispose_engine()

    try:
        return asyncio.run(probe())
    except Exception:  # noqa: BLE001 - availability probe
        return False


DB_AVAILABLE = _db_available()


@pytest.fixture(params=["memory", "pgvector"])
async def store(request: pytest.FixtureRequest) -> AsyncIterator[ContextStore]:
    if request.param == "memory":
        yield MemoryContextStore()
        return
    if not DB_AVAILABLE:
        pytest.skip("no database reachable (docker compose up -d postgres)")
    yield PgVectorContextStore()


@pytest.fixture
async def workspace() -> AsyncIterator[str]:
    name = f"test-{uuid.uuid4().hex[:8]}"
    yield name
    if DB_AVAILABLE:
        async with session_scope() as session:
            await session.execute(delete(Document).where(Document.workspace_id == name))


async def test_ingest_search_and_reingest(store: ContextStore, workspace: str) -> None:
    llm = EchoProvider()
    first = await ingest_document(
        store, llm, workspace_id=workspace, document_id="r.txt", text=REPORT, parser="text"
    )
    again = await ingest_document(
        store, llm, workspace_id=workspace, document_id="r.txt", text=REPORT
    )
    assert first.chunks == 3 and again.unchanged

    hits = await search_store(store, llm, workspace_id=workspace, query=CHUNK_TWO, k=3)
    assert hits[0].chunk.source in {"r.txt:r3", "r.txt:r4"}
    assert hits[0].score == pytest.approx(1.0, abs=1e-4)
    assert [h.score for h in hits] == sorted((h.score for h in hits), reverse=True)

    # A changed file replaces its chunks rather than adding to them.
    await ingest_document(
        store, llm, workspace_id=workspace, document_id="r.txt", text="One line only.\n"
    )
    [document] = await store.documents(workspace)
    assert document.chunks == 1 and document.sha256 and workspace in await store.workspaces()


async def test_search_never_leaves_its_workspace_or_documents(
    store: ContextStore, workspace: str
) -> None:
    llm = EchoProvider()
    other = f"{workspace}-other"
    try:
        await ingest_document(store, llm, workspace_id=workspace, document_id="a.txt", text=REPORT)
        await ingest_document(store, llm, workspace_id=workspace, document_id="b.txt", text=REPORT)
        await ingest_document(store, llm, workspace_id=other, document_id="c.txt", text=REPORT)
        hits = await search_store(
            store, llm, workspace_id=workspace, query=CHUNK_TWO, k=10, document_ids=["b.txt"]
        )
        assert hits and {h.chunk.locator.document_id for h in hits} == {"b.txt"}
    finally:
        if DB_AVAILABLE and isinstance(store, PgVectorContextStore):
            async with session_scope() as session:
                await session.execute(delete(Document).where(Document.workspace_id == other))
