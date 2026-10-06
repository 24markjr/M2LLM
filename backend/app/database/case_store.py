"""The Postgres case store (Phase 44).

`scope` defaults to `session_scope`; the tests pass one bound to a transaction they roll back.
"""

from __future__ import annotations

from collections.abc import Callable
from contextlib import AbstractAsyncContextManager
from datetime import datetime

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.session import session_scope
from app.models.tables import CaseEvidenceRow, CaseInvestigationRow, CaseRow
from app.schemas.case import (
    Case,
    CaseEvidence,
    CaseInvestigation,
    CaseMode,
    CaseSeverity,
    CaseStatus,
)

Scope = Callable[[], AbstractAsyncContextManager[AsyncSession]]


class PgCaseStore:
    name = "postgres"

    def __init__(self, scope: Scope = session_scope) -> None:
        self._scope = scope

    async def next_id(self, year: int) -> str:
        async with self._scope() as session:
            number = (await session.execute(text("SELECT nextval('case_number_seq')"))).scalar_one()
        return f"CASE-{year}-{int(number):05d}"

    async def add(self, case: Case) -> Case:
        async with self._scope() as session:
            session.add(
                CaseRow(
                    case_id=case.case_id,
                    title=case.title,
                    description=case.description,
                    severity=case.severity.value,
                    status=case.status.value,
                    owner=case.owner,
                    mode=case.mode.value,
                    opened_at=case.opened_at,
                    closed_at=case.closed_at,
                )
            )
        return case

    async def get(self, case_id: str) -> Case | None:
        async with self._scope() as session:
            row = await session.get(CaseRow, case_id)
            return _case(row) if row else None

    async def cases(self) -> list[Case]:
        async with self._scope() as session:
            rows = (
                await session.execute(
                    select(CaseRow).order_by(CaseRow.opened_at.desc(), CaseRow.case_id.desc())
                )
            ).scalars()
            return [_case(r) for r in rows]

    async def update(
        self,
        case_id: str,
        *,
        title: str | None = None,
        description: str | None = None,
        severity: CaseSeverity | None = None,
        status: CaseStatus | None = None,
        owner: str | None = None,
        closed_at: datetime | None = None,
    ) -> Case | None:
        async with self._scope() as session:
            row = await session.get(CaseRow, case_id)
            if row is None:
                return None
            if title is not None:
                row.title = title
            if description is not None:
                row.description = description
            if severity is not None:
                row.severity = severity.value
            if owner is not None:
                row.owner = owner
            if status is not None:
                row.status = status.value
                row.closed_at = closed_at if status is CaseStatus.CLOSED else None
            await session.flush()
            return _case(row)

    async def save_investigation(self, investigation: CaseInvestigation) -> None:
        async with self._scope() as session:
            await session.merge(
                CaseInvestigationRow(
                    run_id=investigation.run_id,
                    case_id=investigation.case_id,
                    objective=investigation.objective,
                    status=investigation.status,
                    findings=investigation.findings,
                    verified=investigation.verified,
                    contradictions=investigation.contradictions,
                    open_gaps=investigation.open_gaps,
                    created_at=investigation.created_at,
                    finished_at=investigation.finished_at,
                )
            )

    async def investigations(self, case_id: str) -> list[CaseInvestigation]:
        async with self._scope() as session:
            rows = (
                await session.execute(
                    select(CaseInvestigationRow)
                    .where(CaseInvestigationRow.case_id == case_id)
                    .order_by(CaseInvestigationRow.created_at.desc())
                )
            ).scalars()
            return [
                CaseInvestigation(
                    case_id=r.case_id,
                    run_id=r.run_id,
                    objective=r.objective,
                    status=r.status,
                    findings=r.findings,
                    verified=r.verified,
                    contradictions=r.contradictions,
                    open_gaps=r.open_gaps,
                    created_at=r.created_at,
                    finished_at=r.finished_at,
                )
                for r in rows
            ]

    async def case_of_run(self, run_id: str) -> str | None:
        async with self._scope() as session:
            row = await session.get(CaseInvestigationRow, run_id)
            return row.case_id if row else None

    async def add_evidence(self, link: CaseEvidence) -> bool:
        async with self._scope() as session:
            if await session.get(CaseEvidenceRow, (link.case_id, link.evidence_id)) is not None:
                return False
            session.add(
                CaseEvidenceRow(
                    case_id=link.case_id,
                    evidence_id=link.evidence_id,
                    added_at=link.added_at,
                    added_by=link.added_by,
                )
            )
            return True

    async def evidence(self, case_id: str) -> list[CaseEvidence]:
        async with self._scope() as session:
            rows = (
                await session.execute(
                    select(CaseEvidenceRow)
                    .where(CaseEvidenceRow.case_id == case_id)
                    .order_by(CaseEvidenceRow.added_at)
                )
            ).scalars()
            return [
                CaseEvidence(
                    case_id=r.case_id,
                    evidence_id=r.evidence_id,
                    added_at=r.added_at,
                    added_by=r.added_by,
                )
                for r in rows
            ]

    async def cases_of_evidence(self, evidence_id: str) -> list[str]:
        async with self._scope() as session:
            rows = await session.execute(
                select(CaseEvidenceRow.case_id).where(CaseEvidenceRow.evidence_id == evidence_id)
            )
            return sorted(rows.scalars())


def _case(row: CaseRow) -> Case:
    return Case(
        case_id=row.case_id,
        title=row.title,
        description=row.description,
        severity=CaseSeverity(row.severity),
        status=CaseStatus(row.status),
        owner=row.owner,
        mode=CaseMode(row.mode),
        opened_at=row.opened_at,
        closed_at=row.closed_at,
    )
