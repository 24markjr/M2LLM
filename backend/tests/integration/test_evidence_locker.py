"""Phase 43: the Postgres evidence locker, and the trigger that keeps custody append-only.

Every test runs inside one transaction that is rolled back at the end. That is not a convenience:
custody rows cannot be deleted - that is the point of them - so a test that committed one would
leave it in the developer's database for good.
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator, Callable
from contextlib import AbstractAsyncContextManager, asynccontextmanager

import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncSession, async_sessionmaker

from app.database.evidence_locker import PgEvidenceLocker
from app.database.session import database_available, dispose_engine, get_engine
from app.schemas.evidence_locker import (
    CustodyAction,
    CustodyEvent,
    EvidenceClassification,
    EvidenceItem,
    IntegrityStatus,
)

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
            await session.commit()  # commits the savepoint; the outer transaction is rolled back

    return scope


def _item(evidence_id: str, sha: str, name: str = "report.txt") -> EvidenceItem:
    return EvidenceItem(evidence_id=evidence_id, sha256=sha, name=name)


@requires_db
async def test_items_custody_and_citations_round_trip(connection: AsyncConnection) -> None:
    locker = PgEvidenceLocker(_scope(connection))
    first = await locker.next_id()
    second = await locker.next_id()
    assert first.startswith("EV-") and int(second[3:]) == int(first[3:]) + 1

    await locker.add(_item(first, "a" * 64))
    await locker.add(_item(second, "b" * 64))
    assert (await locker.by_sha("a" * 64)) == await locker.get(first)
    assert (await locker.current_for_name("report.txt")) is not None

    for action, details in [
        (CustodyAction.ACQUIRED, {}),
        (
            CustodyAction.CITED,
            {"run_id": "run_x", "finding_id": "F-001", "locator": "report.txt:r3"},
        ),
    ]:
        await locker.record(CustodyEvent(evidence_id=first, action=action, details=details))
    history = await locker.history(first)
    assert [e.action for e in history] == [CustodyAction.ACQUIRED, CustodyAction.CITED]
    assert history[0].event_id < history[1].event_id
    [citation] = await locker.citations(first)
    assert citation.finding_id == "F-001" and citation.locator == "report.txt:r3"

    updated = await locker.update(
        first, classification=EvidenceClassification.RESTRICTED, integrity=IntegrityStatus.FAILED
    )
    assert updated is not None and updated.classification is EvidenceClassification.RESTRICTED
    assert updated.integrity is IntegrityStatus.FAILED and updated.integrity_checked_at is not None


@requires_db
@pytest.mark.parametrize(
    "statement",
    [
        "UPDATE custody_events SET actor = 'someone else' WHERE evidence_id = :id",
        "DELETE FROM custody_events WHERE evidence_id = :id",
        "TRUNCATE custody_events",
    ],
)
async def test_custody_cannot_be_rewritten_or_erased(
    connection: AsyncConnection, statement: str
) -> None:
    locker = PgEvidenceLocker(_scope(connection))
    evidence_id = await locker.next_id()
    await locker.add(_item(evidence_id, "c" * 64))
    await locker.record(CustodyEvent(evidence_id=evidence_id, action=CustodyAction.ACQUIRED))

    savepoint = await connection.begin_nested()
    with pytest.raises(DBAPIError, match="append-only"):
        await connection.execute(text(statement), {"id": evidence_id})
    await savepoint.rollback()
    assert len(await locker.history(evidence_id)) == 1


@requires_db
async def test_an_item_with_custody_cannot_be_deleted(connection: AsyncConnection) -> None:
    locker = PgEvidenceLocker(_scope(connection))
    evidence_id = await locker.next_id()
    await locker.add(_item(evidence_id, "d" * 64))
    await locker.record(CustodyEvent(evidence_id=evidence_id, action=CustodyAction.ACQUIRED))
    savepoint = await connection.begin_nested()
    with pytest.raises(DBAPIError):
        await connection.execute(
            text("DELETE FROM evidence_items WHERE evidence_id = :id"), {"id": evidence_id}
        )
    await savepoint.rollback()
