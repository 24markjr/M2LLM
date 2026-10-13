"""Cases over HTTP (Phase 44): open a case, file investigations and evidence, follow it to closed.

Every count on a case is computed when asked for, from what the case holds. Every response names
the store that answered: `postgres`, or `memory` when the database is down (cases then not durable).
"""

from __future__ import annotations

import re

from fastapi import APIRouter, Header, Query, status
from pydantic import Field

from app.api.deletion import DeletionReport, delete_case
from app.api.errors import ApiError
from app.api.registry import get_registry
from app.cases.service import counters, file_evidence, get_case_store, this_year
from app.cases.store import CaseStore
from app.evidence.service import get_locker
from app.schemas.case import (
    CASE_ID,
    Case,
    CaseCounters,
    CaseInvestigation,
    CaseMode,
    CaseSeverity,
    CaseStatus,
)
from app.schemas.common import JarvisModel, utcnow
from app.schemas.evidence_locker import EvidenceItem

router = APIRouter(prefix="/cases", tags=["cases"])


class CaseCreate(JarvisModel):
    title: str = Field(min_length=3, max_length=200)
    description: str = Field(default="", max_length=4000)
    severity: CaseSeverity = CaseSeverity.MEDIUM
    owner: str = Field(default="", max_length=128)
    mode: CaseMode = CaseMode.GENERAL


class CaseUpdate(JarvisModel):
    title: str | None = Field(default=None, min_length=3, max_length=200)
    description: str | None = Field(default=None, max_length=4000)
    severity: CaseSeverity | None = None
    status: CaseStatus | None = None
    owner: str | None = Field(default=None, max_length=128)
    mode: CaseMode | None = None
    # Opt-in recall of similar cases as context (Phase 52, D19).
    recall_similar: bool | None = None
    # Phase U1: keep the case at the top of the list. Renaming is `title`.
    pinned: bool | None = None


class CaseSummary(JarvisModel):
    case: Case
    counters: CaseCounters


class CaseList(JarvisModel):
    store: str
    cases: list[CaseSummary] = Field(default_factory=list)


class CaseEvidenceItem(JarvisModel):
    item: EvidenceItem
    added_at: str
    added_by: str


class CaseDetail(JarvisModel):
    store: str
    case: Case
    counters: CaseCounters
    investigations: list[CaseInvestigation] = Field(default_factory=list)
    evidence: list[CaseEvidenceItem] = Field(default_factory=list)


class FileEvidence(JarvisModel):
    evidence_ids: list[str] = Field(min_length=1, max_length=200)


class Filed(JarvisModel):
    case_id: str
    added: int


@router.post("", response_model=Case, status_code=status.HTTP_201_CREATED)
async def open_case(
    body: CaseCreate,
    actor: str = Header(default="console", alias="X-Jarvis-User", max_length=128),
) -> Case:
    store = await get_case_store()
    case = Case(
        case_id=await store.next_id(this_year()),
        title=body.title,
        description=body.description,
        severity=body.severity,
        owner=body.owner or actor,
        mode=body.mode,
    )
    return await store.add(case)


@router.get("", response_model=CaseList)
async def list_cases(q: str = Query(default="", max_length=200)) -> CaseList:
    """Cases, pinned first, then newest. `q` (Phase U1) keeps the cases whose id, title or
    description, or the question of one of their investigations, contains every word of it."""
    store = await get_case_store()
    running = _running()
    found = [c for c in await store.cases() if not q or await _matches(store, c, q)]
    found.sort(key=lambda c: not c.pinned)  # stable: newest-first order kept within each group
    return CaseList(
        store=store.name,
        cases=[
            CaseSummary(case=case, counters=await counters(store, case, running)) for case in found
        ],
    )


async def _matches(store: CaseStore, case: Case, q: str) -> bool:
    words = q.lower().split()
    text = " ".join([case.case_id, case.title, case.description]).lower()
    if all(w in text for w in words):
        return True
    asked = " ".join(i.objective for i in await store.investigations(case.case_id)).lower()
    return all(w in f"{text} {asked}" for w in words)


@router.get("/{case_id}", response_model=CaseDetail)
async def get_case(case_id: str) -> CaseDetail:
    store = await get_case_store()
    case = await _require(store, case_id)
    locker = await get_locker()
    held = []
    for link in await store.evidence(case_id):
        item = await locker.get(link.evidence_id)
        if item is not None:
            held.append(
                CaseEvidenceItem(
                    item=item, added_at=link.added_at.isoformat(), added_by=link.added_by
                )
            )
    return CaseDetail(
        store=store.name,
        case=case,
        counters=await counters(store, case, _running()),
        investigations=await store.investigations(case_id),
        evidence=held,
    )


@router.patch("/{case_id}", response_model=Case)
async def update_case(case_id: str, body: CaseUpdate) -> Case:
    store = await get_case_store()
    await _require(store, case_id)
    updated = await store.update(
        case_id,
        title=body.title,
        description=body.description,
        severity=body.severity,
        status=body.status,
        owner=body.owner,
        closed_at=utcnow() if body.status is CaseStatus.CLOSED else None,
        mode=body.mode,
        recall_similar=body.recall_similar,
        pinned=body.pinned,
    )
    assert updated is not None
    return updated


@router.delete("/{case_id}", response_model=DeletionReport)
async def remove_case(
    case_id: str,
    actor: str = Header(default="console", alias="X-Jarvis-User", max_length=128),
) -> DeletionReport:
    """Delete a case and every investigation in it (Phase U1). Its evidence stays in the Evidence
    Locker; only the case's links to it go."""
    return await delete_case(case_id, actor=actor)


@router.post("/{case_id}/evidence", response_model=Filed)
async def file_case_evidence(
    case_id: str,
    body: FileEvidence,
    actor: str = Header(default="console", alias="X-Jarvis-User", max_length=128),
) -> Filed:
    """File existing evidence items in a case (from the locker, or another case)."""
    store = await get_case_store()
    await _require(store, case_id)
    locker = await get_locker()
    unknown = [e for e in body.evidence_ids if await locker.get(e) is None]
    if unknown:
        raise ApiError(
            "EVIDENCE_NOT_FOUND",
            f"no evidence item {', '.join(unknown)}",
            status_code=status.HTTP_404_NOT_FOUND,
        )
    added = await file_evidence(case_id, body.evidence_ids, actor=actor)
    return Filed(case_id=case_id, added=added)


def _running() -> set[str]:
    return {r.run_id for r in get_registry().records() if not r.is_finished()}


async def _require(store: CaseStore, case_id: str) -> Case:
    case = await store.get(case_id) if re.fullmatch(CASE_ID, case_id) else None
    if case is None:
        raise ApiError(
            "CASE_NOT_FOUND", f"no case {case_id}", status_code=status.HTTP_404_NOT_FOUND
        )
    return case
