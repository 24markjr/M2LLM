"""Phase 50: the Postgres review store, and the triggers that keep decisions and the audit log
append-only.

Every test runs inside one transaction rolled back at the end: neither table can be cleaned up
afterwards - that is the point of them.
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator, Callable
from contextlib import AbstractAsyncContextManager, asynccontextmanager

import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncSession, async_sessionmaker

from app.database.review_store import PgReviewStore
from app.database.session import database_available, dispose_engine, get_engine
from app.schemas.review import AuditEntry, ReviewDecision, ReviewState

pytestmark = pytest.mark.integration


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


requires_db = pytest.mark.skipif(
    not _db_available(), reason="no database reachable (docker compose up -d postgres)"
)

Scope = Callable[[], AbstractAsyncContextManager[AsyncSession]]


@pytest.fixture
async def connection() -> AsyncIterator[AsyncConnection]:
    async with get_engine().connect() as conn:
        outer = await conn.begin()
        try:
            yield conn
        finally:
            await outer.rollback()


def _scope(conn: AsyncConnection) -> Scope:
    maker = async_sessionmaker(bind=conn, join_transaction_mode="create_savepoint")

    @asynccontextmanager
    async def scope() -> AsyncIterator[AsyncSession]:
        async with maker() as session:
            yield session
            await session.commit()

    return scope


@requires_db
async def test_decisions_and_audit_round_trip(connection: AsyncConnection) -> None:
    store = PgReviewStore(_scope(connection))
    first = await store.decide(
        ReviewDecision(
            run_id="run_0123456789ab", finding_id="F-001", state=ReviewState.APPROVED, reviewer="r"
        )
    )
    await store.decide(
        ReviewDecision(
            run_id="run_0123456789ab",
            finding_id="F-001",
            state=ReviewState.REJECTED,
            reviewer="r2",
            reason="the line says otherwise",
        )
    )
    history = await store.decisions("run_0123456789ab")
    assert [d.state for d in history] == [ReviewState.APPROVED, ReviewState.REJECTED]
    assert first.decision_id == history[0].decision_id

    await store.record(AuditEntry(actor="r", action="POST /api/v1/x", target="x", status_code=200))
    [entry] = await store.audit(target="x")
    assert (entry.actor, entry.status_code) == ("r", 200)


@requires_db
@pytest.mark.parametrize(
    "statement",
    [
        "UPDATE review_decisions SET state = 'APPROVED'",
        "DELETE FROM review_decisions",
        "UPDATE audit_log SET actor = 'someone else'",
        "DELETE FROM audit_log",
        "TRUNCATE audit_log",
    ],
)
async def test_neither_can_be_rewritten_or_erased(
    connection: AsyncConnection, statement: str
) -> None:
    store = PgReviewStore(_scope(connection))
    await store.decide(
        ReviewDecision(
            run_id="run_0123456789ab", finding_id="F-001", state=ReviewState.APPROVED, reviewer="r"
        )
    )
    await store.record(AuditEntry(action="system.test"))

    savepoint = await connection.begin_nested()
    with pytest.raises(DBAPIError, match="append-only"):
        await connection.execute(text(statement))
    await savepoint.rollback()
