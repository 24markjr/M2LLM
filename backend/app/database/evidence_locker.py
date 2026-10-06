"""The Postgres evidence locker (Phase 43).

Items in `evidence_items`, custody in `custody_events`, which the database itself keeps append-only
(a trigger rejects UPDATE, DELETE and TRUNCATE). Numbers come from a sequence, so two uploads at the
same moment never get the same `EV-` number.

`scope` is the session factory, `session_scope` by default. The integration tests pass one bound to
a transaction they roll back, so an append-only table is exercised without leaving rows behind.
"""

from __future__ import annotations

from collections.abc import Callable
from contextlib import AbstractAsyncContextManager

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.session import session_scope
from app.evidence.locker import citations_from
from app.models.tables import CustodyEventRow, EvidenceItemRow
from app.schemas.common import utcnow
from app.schemas.evidence_locker import (
    CustodyAction,
    CustodyEvent,
    EvidenceCitation,
    EvidenceClassification,
    EvidenceItem,
    IntegrityStatus,
)

Scope = Callable[[], AbstractAsyncContextManager[AsyncSession]]


class PgEvidenceLocker:
    name = "postgres"

    def __init__(self, scope: Scope = session_scope) -> None:
        self._scope = scope

    async def next_id(self) -> str:
        async with self._scope() as session:
            number = (
                await session.execute(text("SELECT nextval('evidence_number_seq')"))
            ).scalar_one()
        return f"EV-{int(number):06d}"

    async def add(self, item: EvidenceItem) -> EvidenceItem:
        async with self._scope() as session:
            session.add(
                EvidenceItemRow(
                    evidence_id=item.evidence_id,
                    sha256=item.sha256,
                    name=item.name,
                    kind=item.kind,
                    parser=item.parser,
                    bytes=item.bytes,
                    collected_at=item.collected_at,
                    collected_by=item.collected_by,
                    source=item.source,
                    classification=item.classification.value,
                    integrity=item.integrity.value,
                    integrity_checked_at=item.integrity_checked_at,
                    case_id=item.case_id,
                )
            )
        return item

    async def get(self, evidence_id: str) -> EvidenceItem | None:
        async with self._scope() as session:
            row = await session.get(EvidenceItemRow, evidence_id)
            return _item(row) if row else None

    async def by_sha(self, sha256: str) -> EvidenceItem | None:
        return await self._one(select(EvidenceItemRow).where(EvidenceItemRow.sha256 == sha256))

    async def current_for_name(self, name: str) -> EvidenceItem | None:
        return await self._one(
            select(EvidenceItemRow)
            .where(EvidenceItemRow.name == name)
            .order_by(EvidenceItemRow.collected_at.desc(), EvidenceItemRow.evidence_id.desc())
            .limit(1)
        )

    async def items(self, *, limit: int = 200) -> list[EvidenceItem]:
        async with self._scope() as session:
            rows = (
                await session.execute(
                    select(EvidenceItemRow)
                    .order_by(EvidenceItemRow.evidence_id.desc())
                    .limit(limit)
                )
            ).scalars()
            return [_item(r) for r in rows]

    async def update(
        self,
        evidence_id: str,
        *,
        classification: EvidenceClassification | None = None,
        source: str | None = None,
        integrity: IntegrityStatus | None = None,
        kind: str | None = None,
        parser: str | None = None,
    ) -> EvidenceItem | None:
        async with self._scope() as session:
            row = await session.get(EvidenceItemRow, evidence_id)
            if row is None:
                return None
            if classification is not None:
                row.classification = classification.value
            if source is not None:
                row.source = source
            if kind is not None:
                row.kind = kind
            if parser is not None:
                row.parser = parser
            if integrity is not None:
                row.integrity = integrity.value
                row.integrity_checked_at = utcnow()
            await session.flush()
            return _item(row)

    async def record(self, event: CustodyEvent) -> CustodyEvent:
        async with self._scope() as session:
            row = CustodyEventRow(
                evidence_id=event.evidence_id,
                action=event.action.value,
                actor=event.actor,
                at=event.at,
                details=event.details,
            )
            session.add(row)
            await session.flush()
            return event.model_copy(update={"event_id": row.id})

    async def history(self, evidence_id: str) -> list[CustodyEvent]:
        async with self._scope() as session:
            rows = (
                await session.execute(
                    select(CustodyEventRow)
                    .where(CustodyEventRow.evidence_id == evidence_id)
                    .order_by(CustodyEventRow.id)
                )
            ).scalars()
            return [
                CustodyEvent(
                    event_id=r.id,
                    evidence_id=r.evidence_id,
                    action=CustodyAction(r.action),
                    actor=r.actor,
                    at=r.at,
                    details=dict(r.details or {}),
                )
                for r in rows
            ]

    async def citations(self, evidence_id: str) -> list[EvidenceCitation]:
        return citations_from(await self.history(evidence_id))

    async def _one(self, query: object) -> EvidenceItem | None:
        async with self._scope() as session:
            row = (await session.execute(query)).scalars().first()  # type: ignore[call-overload]
            return _item(row) if row else None


def _item(row: EvidenceItemRow) -> EvidenceItem:
    return EvidenceItem(
        evidence_id=row.evidence_id,
        sha256=row.sha256,
        name=row.name,
        kind=row.kind,
        parser=row.parser,
        bytes=row.bytes,
        collected_at=row.collected_at,
        collected_by=row.collected_by,
        source=row.source,
        classification=EvidenceClassification(row.classification),
        integrity=IntegrityStatus(row.integrity),
        integrity_checked_at=row.integrity_checked_at,
        case_id=row.case_id,
    )
