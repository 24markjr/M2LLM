"""The Evidence Locker over HTTP (Phase 43).

Every input as an evidence item: its hash, where it came from, its integrity, and its chain of
custody - acquired, stored, parsed, analysed by which mission, cited by which finding. The chain is
append-only (in Postgres, by a trigger); this API can add to it (a verification, a metadata change)
and never alter it.

Each response names the locker that answered: `postgres`, or `memory` when the database is down -
in which case custody is not durable, and the console says so.
"""

from __future__ import annotations

import re
from pathlib import Path

from fastapi import APIRouter, Header, Query, status
from fastapi.responses import FileResponse
from pydantic import Field

from app.api.errors import ApiError
from app.core.config import get_settings
from app.evidence import service, store
from app.evidence.locker import EvidenceLocker
from app.schemas.common import JarvisModel
from app.schemas.evidence_locker import (
    CustodyAction,
    CustodyEvent,
    EvidenceCitation,
    EvidenceClassification,
    EvidenceItem,
    IntegrityCheck,
)

router = APIRouter(prefix="/evidence", tags=["evidence"])

EVIDENCE_ID = r"^EV-\d{6,}$"


class EvidenceSummary(JarvisModel):
    item: EvidenceItem
    citations: int = 0


class EvidenceList(JarvisModel):
    locker: str
    items: list[EvidenceSummary] = Field(default_factory=list)
    # Files found in the uploads folder and registered by this request (IMPORTED).
    imported: int = 0


class EvidenceDetail(JarvisModel):
    locker: str
    item: EvidenceItem
    custody: list[CustodyEvent] = Field(default_factory=list)
    citations: list[EvidenceCitation] = Field(default_factory=list)
    # Other items that arrived under the same name (earlier or later versions of the file).
    versions: list[EvidenceItem] = Field(default_factory=list)


class EvidenceUpdate(JarvisModel):
    classification: EvidenceClassification | None = None
    source: str | None = Field(default=None, max_length=500)


@router.get("", response_model=EvidenceList)
async def list_evidence(limit: int = Query(default=200, ge=1, le=1000)) -> EvidenceList:
    """Every evidence item, newest first. Uploads that predate the locker are registered here."""
    locker = await service.get_locker()
    imported = await _import_uploads(locker)
    items = await locker.items(limit=limit)
    summaries = [
        EvidenceSummary(item=item, citations=len(await locker.citations(item.evidence_id)))
        for item in items
    ]
    return EvidenceList(locker=locker.name, items=summaries, imported=imported)


@router.get("/by-name/{name}", response_model=EvidenceItem)
async def evidence_by_name(name: str) -> EvidenceItem:
    """The current item for a document name: the version a new mission naming it would read."""
    locker = await service.get_locker()
    item = await locker.current_for_name(name)
    if item is None:
        raise _not_found(name)
    return item


@router.get("/{evidence_id}", response_model=EvidenceDetail)
async def get_evidence(evidence_id: str) -> EvidenceDetail:
    locker = await service.get_locker()
    item = await _require(locker, evidence_id)
    history = await locker.history(evidence_id)
    versions = [
        v
        for v in await locker.items(limit=1000)
        if v.name == item.name and v.evidence_id != evidence_id
    ]
    return EvidenceDetail(
        locker=locker.name,
        item=item,
        custody=history,
        citations=await locker.citations(evidence_id),
        versions=versions,
    )


@router.get("/{evidence_id}/custody", response_model=list[CustodyEvent])
async def get_custody(evidence_id: str) -> list[CustodyEvent]:
    locker = await service.get_locker()
    await _require(locker, evidence_id)
    return await locker.history(evidence_id)


@router.get("/{evidence_id}/findings", response_model=list[EvidenceCitation])
async def get_citations(evidence_id: str) -> list[EvidenceCitation]:
    """The findings that cited this item, from its CITED custody events."""
    locker = await service.get_locker()
    await _require(locker, evidence_id)
    return await locker.citations(evidence_id)


@router.post("/{evidence_id}/verify", response_model=IntegrityCheck)
async def verify_evidence(
    evidence_id: str,
    actor: str = Header(default="console", alias="X-Jarvis-User", max_length=128),
) -> IntegrityCheck:
    """Re-hash the stored original and, for the current version of a name, the working copy."""
    locker = await service.get_locker()
    item = await _require(locker, evidence_id)
    current = await locker.current_for_name(item.name)
    working = (
        _working_copy(item.name)
        if current is not None and current.evidence_id == evidence_id
        else None
    )
    return await service.verify(locker, item, working, actor=actor)


@router.patch("/{evidence_id}", response_model=EvidenceItem)
async def update_evidence(
    evidence_id: str,
    body: EvidenceUpdate,
    actor: str = Header(default="console", alias="X-Jarvis-User", max_length=128),
) -> EvidenceItem:
    """Change what a person decides about an item. Recorded as METADATA_CHANGED, old and new."""
    locker = await service.get_locker()
    item = await _require(locker, evidence_id)
    changes: dict[str, dict[str, str]] = {}
    if body.classification is not None and body.classification is not item.classification:
        changes["classification"] = {"from": item.classification, "to": body.classification}
    if body.source is not None and body.source != item.source:
        changes["source"] = {"from": item.source, "to": body.source}
    if not changes:
        return item
    updated = await locker.update(
        evidence_id, classification=body.classification, source=body.source
    )
    await service.note(locker, evidence_id, CustodyAction.METADATA_CHANGED, actor=actor, **changes)
    return updated or item


@router.get("/{evidence_id}/download")
async def download_evidence(evidence_id: str) -> FileResponse:
    """The stored original, byte for byte, under its original name."""
    locker = await service.get_locker()
    item = await _require(locker, evidence_id)
    path = store.path_for(item.sha256)
    if not path.is_file():
        raise ApiError(
            "EVIDENCE_MISSING",
            f"{evidence_id}'s stored original is missing; verify it to record the failure",
            status_code=status.HTTP_410_GONE,
        )
    return FileResponse(path, filename=item.name, media_type="application/octet-stream")


async def _require(locker: EvidenceLocker, evidence_id: str) -> EvidenceItem:
    item = await locker.get(evidence_id) if _valid(evidence_id) else None
    if item is None:
        raise _not_found(evidence_id)
    return item


def _valid(evidence_id: str) -> bool:
    return re.fullmatch(EVIDENCE_ID, evidence_id) is not None


def _not_found(what: str) -> ApiError:
    return ApiError(
        "EVIDENCE_NOT_FOUND",
        f"no evidence item {what}",
        status_code=status.HTTP_404_NOT_FOUND,
    )


def _working_copy(name: str) -> Path | None:
    from app.tools.loader import resolve_document

    path = resolve_document(name)
    return path if path.is_file() else None


async def _import_uploads(locker: EvidenceLocker) -> int:
    """Register uploads that arrived before the locker existed, once (IMPORTED)."""
    folder = get_settings().agent_dir / "uploads"
    if not folder.is_dir():
        return 0
    count = 0
    for path in sorted(folder.iterdir()):
        if not path.is_file() or path.name.startswith(".") or path.suffix == ".part":
            continue
        if await locker.current_for_name(path.name) is not None:
            continue
        await service.register(locker, path, name=path.name)
        count += 1
    return count
