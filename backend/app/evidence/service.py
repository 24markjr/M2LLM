"""Evidence intake, custody and integrity: what uploads, missions and the API call (Phase 43).

Every input becomes an evidence item the first time anything touches it:

- an **upload** is acquired, hashed and stored here, then parsed, understood and indexed;
- a **fixture or earlier upload** a mission reads is registered on first use as IMPORTED, its
  history before that unknown, and said to be.

**Integrity is checked whenever a mission is about to read evidence.** The stored original and the
working copy missions parse must both still hash to the recorded SHA-256. If either does not, the
item is marked FAILED, the event is recorded, and the mission leaves the file out and says so;
findings that already cited it show the failure through its evidence page.

File work (hashing, copying - a video can be 500 MB) runs on a worker thread, never on the event
loop that serves every other request.

**Never failing the caller.** A locker that is unreachable or broken must not fail an upload or a
mission (invariant 10): every function here logs and degrades. What degrades is said: the locker in
use is named, and `memory` means custody is not durable.
"""

from __future__ import annotations

import asyncio
from collections.abc import Iterable
from pathlib import Path
from typing import Any

from app.core.logging import get_logger
from app.evidence import store
from app.evidence.authority import tier_for_name
from app.evidence.locker import EvidenceLocker, MemoryEvidenceLocker
from app.schemas.evidence_locker import (
    CustodyAction,
    CustodyEvent,
    EvidenceItem,
    IntegrityCheck,
    IntegrityStatus,
)

log = get_logger(__name__)

_memory_locker = MemoryEvidenceLocker()
# Probed once per process, like run persistence; unit tests set it False (tests/conftest.py).
_database: bool | None = None


def reset_locker_probe() -> None:
    global _database
    _database = None


async def get_locker() -> EvidenceLocker:
    global _database
    if _database is None:
        from app.database.session import database_available

        _database = await database_available()
    if _database:
        from app.database.evidence_locker import PgEvidenceLocker

        return PgEvidenceLocker()
    return _memory_locker


async def note(
    locker: EvidenceLocker,
    evidence_id: str,
    action: CustodyAction,
    *,
    actor: str = "system",
    **details: Any,
) -> None:
    """Add one link to an item's chain. Never raises."""
    try:
        await locker.record(
            CustodyEvent(evidence_id=evidence_id, action=action, actor=actor, details=details)
        )
    except Exception as exc:  # noqa: BLE001 - custody must never fail the work it records
        log.warning("custody_not_recorded", evidence_id=evidence_id, action=action, error=str(exc))


async def intake(
    locker: EvidenceLocker,
    path: Path,
    *,
    name: str,
    actor: str = "unknown",
    source: str = "uploaded through the console",
) -> EvidenceItem:
    """Acquire a file just written to `path`: store the original, then record acquired, hashed and
    stored. The same bytes again are the same item, acquired again."""
    size = (await asyncio.to_thread(path.stat)).st_size
    sha, stored_at = await asyncio.to_thread(store.put, path)
    item = await locker.by_sha(sha)
    if item is None:
        authority, reason = tier_for_name(name)
        item = await locker.add(
            EvidenceItem(
                evidence_id=await locker.next_id(),
                sha256=sha,
                name=name,
                bytes=size,
                collected_by=actor,
                source=source,
                authority=authority,
                authority_reason=reason,
                integrity=IntegrityStatus.VERIFIED,
            )
        )
    await note(locker, item.evidence_id, CustodyAction.ACQUIRED, actor=actor, name=name, bytes=size)
    await note(locker, item.evidence_id, CustodyAction.HASHED, sha256=sha)
    await note(
        locker,
        item.evidence_id,
        CustodyAction.STORED,
        at=str(stored_at.relative_to(store.evidence_root().parent)),
    )
    return item


async def register(locker: EvidenceLocker, path: Path, *, name: str) -> EvidenceItem:
    """The item for a file a mission is about to read, registering it if it was never acquired.

    Files present before the locker existed - fixtures, earlier uploads - enter as IMPORTED, with
    the reason that their earlier history is unknown. The current item for the name is used when
    its hash still matches; otherwise the bytes are a different item.
    """
    sha = await asyncio.to_thread(store.hash_file, path)
    item = await locker.by_sha(sha)
    if item is not None:
        return item
    await asyncio.to_thread(store.put, path)
    size = (await asyncio.to_thread(path.stat)).st_size
    fixture = "fixtures" in path.parts
    authority, reason = tier_for_name(name)
    item = await locker.add(
        EvidenceItem(
            evidence_id=await locker.next_id(),
            sha256=sha,
            name=name,
            bytes=size,
            collected_by="system",
            source="repository fixture" if fixture else "found in the uploads folder",
            authority=authority,
            authority_reason=reason,
            integrity=IntegrityStatus.VERIFIED,
        )
    )
    await note(
        locker,
        item.evidence_id,
        CustodyAction.IMPORTED,
        reason="present before it was registered; earlier history unknown",
        path=str(path.name),
    )
    return item


async def verify(
    locker: EvidenceLocker,
    item: EvidenceItem,
    working: Path | None = None,
    *,
    actor: str = "system",
) -> IntegrityCheck:
    """Re-hash the stored original (and the working copy, when given) against the record.

    A mismatch marks the item FAILED and records INTEGRITY_FAILED; a match after a failure restores
    it. An explicit check records VERIFIED; the routine check before a mission does not (it would
    add a link per mission per file and say nothing new), but its result is on the ANALYSED event.
    """
    stored, current = await asyncio.to_thread(_hashes, item.sha256, working)
    problems = []
    if stored != item.sha256:
        problems.append(
            "the stored original is missing" if stored is None else "the stored original changed"
        )
    if working is not None and current is not None and current != item.sha256:
        problems.append("the working copy missions read changed")
    status = IntegrityStatus.FAILED if problems else IntegrityStatus.VERIFIED
    result = IntegrityCheck(
        evidence_id=item.evidence_id,
        integrity=status,
        expected=item.sha256,
        stored=stored,
        working=current,
        reason="; ".join(problems),
    )
    try:
        if status is not item.integrity or actor != "system":
            await locker.update(item.evidence_id, integrity=status)
    except Exception as exc:  # noqa: BLE001
        log.warning("integrity_not_saved", evidence_id=item.evidence_id, error=str(exc))
    if problems:
        await note(
            locker,
            item.evidence_id,
            CustodyAction.INTEGRITY_FAILED,
            actor=actor,
            reason=result.reason,
            stored=stored,
            working=current,
        )
    elif actor != "system":
        await note(
            locker, item.evidence_id, CustodyAction.VERIFIED, actor=actor, sha256=item.sha256
        )
    return result


async def admit_for_mission(
    paths: dict[str, Path],
) -> tuple[dict[str, str], dict[str, str]]:
    """Register and check every document a mission is about to read.

    Returns `(admitted, excluded)`: document name to evidence id for files that passed, and name to
    the reason for files that failed integrity. A broken locker admits everything with no ids:
    custody is lost for that mission, and the log says so - the mission itself must not fail.
    """
    admitted: dict[str, str] = {}
    excluded: dict[str, str] = {}
    try:
        locker = await get_locker()
        for name, path in paths.items():
            if not await asyncio.to_thread(path.is_file):
                continue
            item = await _expected(locker, path, name)
            check = await verify(locker, item, path)
            if check.integrity is IntegrityStatus.FAILED:
                excluded[name] = f"{item.evidence_id} failed its integrity check: {check.reason}"
            else:
                admitted[name] = item.evidence_id
    except Exception as exc:  # noqa: BLE001 - optional infrastructure never fails a run
        log.warning("evidence_admission_failed", error=f"{type(exc).__name__}: {exc}")
        return {}, {}
    return admitted, excluded


async def _expected(locker: EvidenceLocker, path: Path, name: str) -> EvidenceItem:
    """The item a mission's file must match.

    For an upload, the one last acquired under its name: only intake writes the uploads folder, so
    a working copy that no longer matches it was changed behind custody's back - an integrity
    failure, not a new version. (Found by Phase 43's own test: looking the file up by its new hash
    registered the tampered bytes as a fresh item.) A repository fixture changes through version
    control, not intake, so changed bytes there are a new version, imported and said to be.
    """
    current = await locker.current_for_name(name)
    if current is not None and "fixtures" not in path.parts:
        return current
    return await register(locker, path, name=name)


async def assess_unassessed(locker: EvidenceLocker) -> int:
    """Give items filed before Phase 45 the tier the intake rules give their name, recorded as
    METADATA_CHANGED. Only items nobody has assessed (no reason recorded); returns how many."""
    changed = 0
    for item in await locker.items(limit=10_000):
        if item.authority_reason:
            continue
        tier, reason = tier_for_name(item.name)
        reason = reason.replace("set at intake", "assessed by the intake rules (filed earlier)")
        await locker.update(item.evidence_id, authority=tier, authority_reason=reason)
        await note(
            locker,
            item.evidence_id,
            CustodyAction.METADATA_CHANGED,
            authority={"from": item.authority, "to": tier},
            reason=reason,
        )
        changed += 1
    return changed


async def authority_of(evidence: dict[str, str]) -> dict[str, str]:
    """Each admitted document's authority tier, from its evidence item (Phase 45). A document whose
    item cannot be read is left out, and the mission falls back to the intake rules for it."""
    tiers: dict[str, str] = {}
    try:
        locker = await get_locker()
        for name, evidence_id in evidence.items():
            item = await locker.get(evidence_id)
            if item is not None:
                tiers[name] = item.authority
    except Exception as exc:  # noqa: BLE001 - optional infrastructure never fails a run
        log.warning("authority_lookup_failed", error=f"{type(exc).__name__}: {exc}")
    return tiers


async def record_analysed(run_id: str, evidence: dict[str, str]) -> None:
    try:
        locker = await get_locker()
    except Exception:  # noqa: BLE001
        return
    for name, evidence_id in evidence.items():
        await note(
            locker,
            evidence_id,
            CustodyAction.ANALYSED,
            run_id=run_id,
            name=name,
            integrity="VERIFIED",
        )


async def record_citations(
    run_id: str, evidence: dict[str, str], citations: Iterable[tuple[str, str, str, str]]
) -> int:
    """CITED once per (finding, locator): `citations` are (finding id, claim, document, locator)."""
    try:
        locker = await get_locker()
    except Exception:  # noqa: BLE001
        return 0
    count = 0
    for finding_id, claim, document, locator in citations:
        evidence_id = evidence.get(document)
        if evidence_id is None:
            continue
        await note(
            locker,
            evidence_id,
            CustodyAction.CITED,
            run_id=run_id,
            finding_id=finding_id,
            locator=locator,
            claim=claim[:200],
        )
        count += 1
    return count


def _hashes(sha256: str, working: Path | None) -> tuple[str | None, str | None]:
    """The stored original's hash and the working copy's (None where a file is missing)."""
    current = store.hash_file(working) if working is not None and working.is_file() else None
    return store.rehash(sha256), current
