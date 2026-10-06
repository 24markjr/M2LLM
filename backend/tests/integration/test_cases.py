"""Phase 44: the Postgres case store, inside one transaction rolled back at the end."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator, Callable
from contextlib import AbstractAsyncContextManager, asynccontextmanager

import pytest
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncSession, async_sessionmaker

from app.database.case_store import PgCaseStore
from app.database.evidence_locker import PgEvidenceLocker
from app.database.session import database_available, dispose_engine, get_engine
from app.schemas.case import Case, CaseEvidence, CaseInvestigation, CaseSeverity, CaseStatus
from app.schemas.common import utcnow
from app.schemas.evidence_locker import EvidenceItem

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
async def scope() -> AsyncIterator[Scope]:
    async with get_engine().connect() as conn:
        outer = await conn.begin()
        try:
            yield _scope(conn)
        finally:
            await outer.rollback()


def _scope(conn: AsyncConnection) -> Scope:
    maker = async_sessionmaker(bind=conn, join_transaction_mode="create_savepoint")

    @asynccontextmanager
    async def session() -> AsyncIterator[AsyncSession]:
        async with maker() as s:
            yield s
            await s.commit()

    return session


@requires_db
async def test_cases_investigations_and_evidence_round_trip(scope: Scope) -> None:
    store = PgCaseStore(scope)
    first = await store.next_id(2026)
    second = await store.next_id(2026)
    assert first.startswith("CASE-2026-") and int(second[-5:]) == int(first[-5:]) + 1

    case = await store.add(Case(case_id=first, title="Helix budget", severity=CaseSeverity.HIGH))
    assert (await store.get(first)) == case
    assert first in [c.case_id for c in await store.cases()]

    closed = await store.update(first, status=CaseStatus.CLOSED, closed_at=utcnow())
    assert closed is not None and closed.closed_at is not None
    reopened = await store.update(first, status=CaseStatus.INVESTIGATING)
    assert reopened is not None and reopened.closed_at is None

    pending = CaseInvestigation(case_id=first, run_id="run_aaaaaaaaaaaa", objective="x")
    await store.save_investigation(pending)
    await store.save_investigation(
        pending.model_copy(update={"status": "COMPLETED", "findings": 2})
    )
    [saved] = await store.investigations(first)
    assert saved.status == "COMPLETED" and saved.findings == 2  # replaced, not duplicated
    assert await store.case_of_run("run_aaaaaaaaaaaa") == first

    locker = PgEvidenceLocker(scope)
    evidence_id = await locker.next_id()
    await locker.add(EvidenceItem(evidence_id=evidence_id, sha256="e" * 64, name="a.txt"))
    link = CaseEvidence(case_id=first, evidence_id=evidence_id)
    assert await store.add_evidence(link) is True
    assert await store.add_evidence(link) is False
    assert [e.evidence_id for e in await store.evidence(first)] == [evidence_id]
    assert await store.cases_of_evidence(evidence_id) == [first]
