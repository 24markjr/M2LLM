"""Where cases and their links are kept (Phase 44).

One protocol, two stores, as for the Evidence Locker: Postgres (`app/database/case_store.py`) when
the database answers, memory otherwise - named, so the console can say cases are not durable.
"""

from __future__ import annotations

from datetime import datetime
from typing import Protocol

from app.schemas.case import (
    Case,
    CaseEvidence,
    CaseInvestigation,
    CaseMode,
    CaseSeverity,
    CaseStatus,
)


class CaseStore(Protocol):
    name: str

    async def next_id(self, year: int) -> str: ...

    async def add(self, case: Case) -> Case: ...

    async def get(self, case_id: str) -> Case | None: ...

    async def cases(self) -> list[Case]: ...

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
        mode: CaseMode | None = None,
        recall_similar: bool | None = None,
    ) -> Case | None: ...

    async def save_investigation(self, investigation: CaseInvestigation) -> None:
        """Insert or replace by run id."""
        ...

    async def investigations(self, case_id: str) -> list[CaseInvestigation]: ...

    async def case_of_run(self, run_id: str) -> str | None: ...

    async def add_evidence(self, link: CaseEvidence) -> bool:
        """False when the case already held it."""
        ...

    async def evidence(self, case_id: str) -> list[CaseEvidence]: ...

    async def cases_of_evidence(self, evidence_id: str) -> list[str]: ...

    # Phase U1: deletion. Evidence items themselves are never deleted, only a case's links to them.
    async def remove_investigation(self, run_id: str) -> bool: ...

    async def delete(self, case_id: str) -> bool: ...


class MemoryCaseStore:
    name = "memory"

    def __init__(self) -> None:
        self._cases: dict[str, Case] = {}
        self._investigations: dict[str, CaseInvestigation] = {}
        self._evidence: dict[tuple[str, str], CaseEvidence] = {}
        self._counter = 0

    async def next_id(self, year: int) -> str:
        self._counter += 1
        return f"CASE-{year}-{self._counter:05d}"

    async def add(self, case: Case) -> Case:
        self._cases[case.case_id] = case
        return case

    async def get(self, case_id: str) -> Case | None:
        return self._cases.get(case_id)

    async def cases(self) -> list[Case]:
        return sorted(self._cases.values(), key=lambda c: (c.opened_at, c.case_id), reverse=True)

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
        mode: CaseMode | None = None,
        recall_similar: bool | None = None,
    ) -> Case | None:
        case = self._cases.get(case_id)
        if case is None:
            return None
        changes: dict[str, object] = {
            k: v
            for k, v in {
                "title": title,
                "description": description,
                "severity": severity,
                "status": status,
                "owner": owner,
                "mode": mode,
                "recall_similar": recall_similar,
            }.items()
            if v is not None
        }
        if status is not None:
            changes["closed_at"] = closed_at if status is CaseStatus.CLOSED else None
        updated = case.model_copy(update=changes)
        self._cases[case_id] = updated
        return updated

    async def save_investigation(self, investigation: CaseInvestigation) -> None:
        self._investigations[investigation.run_id] = investigation

    async def investigations(self, case_id: str) -> list[CaseInvestigation]:
        found = [i for i in self._investigations.values() if i.case_id == case_id]
        return sorted(found, key=lambda i: i.created_at, reverse=True)

    async def case_of_run(self, run_id: str) -> str | None:
        found = self._investigations.get(run_id)
        return found.case_id if found else None

    async def add_evidence(self, link: CaseEvidence) -> bool:
        key = (link.case_id, link.evidence_id)
        if key in self._evidence:
            return False
        self._evidence[key] = link
        return True

    async def evidence(self, case_id: str) -> list[CaseEvidence]:
        found = [e for (c, _), e in self._evidence.items() if c == case_id]
        return sorted(found, key=lambda e: e.added_at)

    async def cases_of_evidence(self, evidence_id: str) -> list[str]:
        return sorted(c for (c, e) in self._evidence if e == evidence_id)

    async def remove_investigation(self, run_id: str) -> bool:
        return self._investigations.pop(run_id, None) is not None

    async def delete(self, case_id: str) -> bool:
        if case_id not in self._cases:
            return False
        for key in [k for k in self._evidence if k[0] == case_id]:
            del self._evidence[key]
        for run_id in [r for r, i in self._investigations.items() if i.case_id == case_id]:
            del self._investigations[run_id]
        del self._cases[case_id]
        return True
