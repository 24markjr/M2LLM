"""The Postgres review store (Phase 50): decisions and the audit log, both append-only by trigger.

`scope` defaults to `session_scope`; the tests pass one bound to a transaction they roll back.
"""

from __future__ import annotations

from collections.abc import Callable
from contextlib import AbstractAsyncContextManager

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.tenancy import current_org
from app.database.session import session_scope
from app.models.tables import AuditLogRow, ReviewDecisionRow
from app.schemas.review import AuditEntry, ReviewDecision, ReviewState

Scope = Callable[[], AbstractAsyncContextManager[AsyncSession]]


class PgReviewStore:
    name = "postgres"

    def __init__(self, scope: Scope = session_scope) -> None:
        self._scope = scope

    async def decide(self, decision: ReviewDecision) -> ReviewDecision:
        async with self._scope() as session:
            row = ReviewDecisionRow(
                run_id=decision.run_id,
                finding_id=decision.finding_id,
                state=decision.state.value,
                reviewer=decision.reviewer,
                reason=decision.reason,
                modified_claim=decision.modified_claim,
                at=decision.at,
            )
            session.add(row)
            await session.flush()
            return decision.model_copy(update={"decision_id": row.id})

    async def decisions(self, run_id: str) -> list[ReviewDecision]:
        async with self._scope() as session:
            rows = (
                await session.execute(
                    select(ReviewDecisionRow)
                    .where(ReviewDecisionRow.run_id == run_id)
                    .order_by(ReviewDecisionRow.id)
                )
            ).scalars()
            return [
                ReviewDecision(
                    decision_id=r.id,
                    run_id=r.run_id,
                    finding_id=r.finding_id,
                    state=ReviewState(r.state),
                    reviewer=r.reviewer,
                    reason=r.reason,
                    modified_claim=r.modified_claim,
                    at=r.at,
                )
                for r in rows
            ]

    async def record(self, entry: AuditEntry) -> AuditEntry:
        async with self._scope() as session:
            row = AuditLogRow(
                at=entry.at,
                actor=entry.actor,
                action=entry.action,
                target=entry.target,
                status_code=entry.status_code,
                details=entry.details,
                org_id=current_org(),
            )
            session.add(row)
            await session.flush()
            return entry.model_copy(update={"entry_id": row.id})

    async def audit(self, *, limit: int = 200, target: str = "") -> list[AuditEntry]:
        async with self._scope() as session:
            query = (
                select(AuditLogRow)
                .where(AuditLogRow.org_id == current_org())
                .order_by(AuditLogRow.id.desc())
                .limit(limit)
            )
            if target:
                query = query.where(
                    or_(AuditLogRow.target.contains(target), AuditLogRow.action.contains(target))
                )
            rows = (await session.execute(query)).scalars()
            return [
                AuditEntry(
                    entry_id=r.id,
                    at=r.at,
                    actor=r.actor,
                    action=r.action,
                    target=r.target,
                    status_code=r.status_code,
                    details=dict(r.details or {}),
                )
                for r in rows
            ]
