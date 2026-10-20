"""Where evidence items and their custody are kept (Phase 43).

One protocol, two stores, as for the knowledge graph and retrieval: Postgres
(`app/database/evidence_locker.py`, custody append-only by a database trigger) and memory. The
memory locker is used when the database does not answer; it is lost on restart and says so by its
name, which the API and the Evidence Locker page show. Custody that is not durable is labelled as
such, never passed off as a record.
"""

from __future__ import annotations

from typing import Protocol

from app.schemas.common import utcnow
from app.schemas.evidence_locker import (
    CustodyAction,
    CustodyEvent,
    EvidenceCitation,
    EvidenceClassification,
    EvidenceItem,
    IntegrityStatus,
)


class EvidenceLocker(Protocol):
    name: str

    async def next_id(self) -> str: ...

    async def add(self, item: EvidenceItem) -> EvidenceItem: ...

    async def get(self, evidence_id: str) -> EvidenceItem | None: ...

    async def by_sha(self, sha256: str) -> EvidenceItem | None: ...

    async def current_for_name(self, name: str) -> EvidenceItem | None:
        """The newest item that arrived under this name: the one a mission naming it reads."""
        ...

    async def items(self, *, limit: int = 200) -> list[EvidenceItem]: ...

    async def update(
        self,
        evidence_id: str,
        *,
        classification: EvidenceClassification | None = None,
        source: str | None = None,
        integrity: IntegrityStatus | None = None,
        kind: str | None = None,
        parser: str | None = None,
        authority: str | None = None,
        authority_reason: str | None = None,
        case_id: str | None = None,
    ) -> EvidenceItem | None: ...

    async def record(self, event: CustodyEvent) -> CustodyEvent: ...

    async def history(self, evidence_id: str) -> list[CustodyEvent]: ...

    async def citations(self, evidence_id: str) -> list[EvidenceCitation]: ...


def citations_from(history: list[CustodyEvent]) -> list[EvidenceCitation]:
    return [
        EvidenceCitation(
            run_id=str(e.details.get("run_id", "")),
            finding_id=str(e.details.get("finding_id", "")),
            locator=str(e.details.get("locator", "")),
            claim=str(e.details.get("claim", "")),
            at=e.at,
        )
        for e in history
        if e.action is CustodyAction.CITED
    ]


class MemoryEvidenceLocker:
    name = "memory"

    def __init__(self) -> None:
        self._items: dict[str, EvidenceItem] = {}
        self._events: list[CustodyEvent] = []
        self._counter = 0

    async def next_id(self) -> str:
        self._counter += 1
        return f"EV-{self._counter:06d}"

    async def add(self, item: EvidenceItem) -> EvidenceItem:
        self._items[item.evidence_id] = item
        return item

    async def get(self, evidence_id: str) -> EvidenceItem | None:
        return self._items.get(evidence_id)

    async def by_sha(self, sha256: str) -> EvidenceItem | None:
        return next((i for i in self._items.values() if i.sha256 == sha256), None)

    async def current_for_name(self, name: str) -> EvidenceItem | None:
        named = [i for i in self._items.values() if i.name == name]
        return max(named, key=lambda i: (i.collected_at, i.evidence_id), default=None)

    async def items(self, *, limit: int = 200) -> list[EvidenceItem]:
        return sorted(self._items.values(), key=lambda i: i.evidence_id, reverse=True)[:limit]

    async def update(
        self,
        evidence_id: str,
        *,
        classification: EvidenceClassification | None = None,
        source: str | None = None,
        integrity: IntegrityStatus | None = None,
        kind: str | None = None,
        parser: str | None = None,
        authority: str | None = None,
        authority_reason: str | None = None,
        case_id: str | None = None,
    ) -> EvidenceItem | None:
        item = self._items.get(evidence_id)
        if item is None:
            return None
        changes: dict[str, object] = {
            k: v
            for k, v in {
                "classification": classification,
                "source": source,
                "integrity": integrity,
                "kind": kind,
                "parser": parser,
                "authority": authority,
                "authority_reason": authority_reason,
            }.items()
            if v is not None
        }
        if integrity is not None:
            changes["integrity_checked_at"] = utcnow()
        # Filing (U8): "" takes an item out of its case.
        if case_id is not None:
            changes["case_id"] = case_id or None
        updated = item.model_copy(update=changes)
        self._items[evidence_id] = updated
        return updated

    async def record(self, event: CustodyEvent) -> CustodyEvent:
        stored = event.model_copy(update={"event_id": len(self._events) + 1})
        self._events.append(stored)
        return stored

    async def history(self, evidence_id: str) -> list[CustodyEvent]:
        return [e for e in self._events if e.evidence_id == evidence_id]

    async def citations(self, evidence_id: str) -> list[EvidenceCitation]:
        return citations_from(await self.history(evidence_id))
