"""Where review decisions and the audit log are kept (Phase 50): append-only, both of them."""

from __future__ import annotations

from typing import Protocol

from app.auth.tenancy import current_org
from app.schemas.review import AuditEntry, ReviewDecision


class ReviewStore(Protocol):
    name: str

    async def decide(self, decision: ReviewDecision) -> ReviewDecision: ...

    async def decisions(self, run_id: str) -> list[ReviewDecision]: ...

    async def record(self, entry: AuditEntry) -> AuditEntry: ...

    async def audit(self, *, limit: int = 200, target: str = "") -> list[AuditEntry]: ...


class MemoryReviewStore:
    name = "memory"

    def __init__(self) -> None:
        self._decisions: list[ReviewDecision] = []
        self._audit: list[AuditEntry] = []
        self._audit_orgs: list[str] = []  # each entry's organisation (v4 Phase 1c)

    async def decide(self, decision: ReviewDecision) -> ReviewDecision:
        stored = decision.model_copy(update={"decision_id": len(self._decisions) + 1})
        self._decisions.append(stored)
        return stored

    async def decisions(self, run_id: str) -> list[ReviewDecision]:
        return [d for d in self._decisions if d.run_id == run_id]

    async def record(self, entry: AuditEntry) -> AuditEntry:
        stored = entry.model_copy(update={"entry_id": len(self._audit) + 1})
        self._audit.append(stored)
        self._audit_orgs.append(current_org())
        return stored

    async def audit(self, *, limit: int = 200, target: str = "") -> list[AuditEntry]:
        org = current_org()
        mine = [e for e, o in zip(self._audit, self._audit_orgs, strict=True) if o == org]
        rows = [e for e in mine if not target or target in e.target or target in e.action]
        return list(reversed(rows))[:limit]
