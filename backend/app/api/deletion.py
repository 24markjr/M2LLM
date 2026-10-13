"""Deleting investigations and cases (Phase U1), and saying exactly what went and what stayed.

An investigation lives in several places: the registry, its archive, its recordings, the stored run
in Postgres (with its tasks, findings, events and episodic memory, by cascade), the facts it
supported in semantic memory, and its case's list. Deleting it removes it from every one of them.

Three records are kept, by design, and the result says so each time:

- the evidence's **chain of custody** - it records that a mission read and cited the evidence, and
  is append-only by database trigger (Phase 43);
- **review decisions** - append-only (Phase 50);
- the **audit log** - append-only, and it gains an entry naming who deleted what.

Evidence items are never deleted with a case: they can belong to other cases, and an item's
existence is part of its custody. Only the case's links to them go.
"""

from __future__ import annotations

from fastapi import status
from pydantic import Field

from app.api.archive import delete_archive
from app.api.errors import ApiError, MissionNotFoundError
from app.api.persistence import persistence_enabled
from app.api.recording import delete_recording, list_recordings
from app.api.registry import get_registry
from app.api.v1.memory import forget_quietly
from app.cases.service import get_case_store
from app.core.logging import get_logger
from app.database.repositories import RunRepository
from app.database.session import session_scope
from app.review.service import audit
from app.schemas.common import JarvisModel

log = get_logger(__name__)

KEPT = [
    "the evidence's chain of custody (append-only)",
    "review decisions (append-only)",
    "the audit log, with this deletion in it",
]


class DeletionReport(JarvisModel):
    deleted: list[str] = Field(default_factory=list)
    removed: list[str] = Field(default_factory=list)
    kept: list[str] = Field(default_factory=lambda: list(KEPT))
    skipped: list[str] = Field(default_factory=list)


async def delete_investigation(run_id: str, *, actor: str) -> DeletionReport:
    """Delete one finished investigation everywhere it is held. A running one is refused."""
    registry = get_registry()
    record = registry.get(run_id)
    if record is None:
        raise MissionNotFoundError(run_id)
    if not record.is_finished():
        raise ApiError(
            "MISSION_RUNNING",
            "the investigation is still running; cancel it first",
            status_code=status.HTTP_409_CONFLICT,
            run_id=run_id,
        )
    removed: list[str] = []
    registry.forget(run_id)
    removed.append("the investigation")
    if delete_archive(run_id):
        removed.append("its archive")
    recordings = [r for r in list_recordings() if r["run_id"] == run_id]
    if any(delete_recording(str(r["file"])) == "deleted" for r in recordings):
        removed.append("its recording")
    if await persistence_enabled():
        try:
            async with session_scope() as session:
                runs = RunRepository(session)
                if await runs.get(run_id) is not None:
                    await runs.delete(run_id)
                    removed.append("the stored run: tasks, findings, events, episodes")
        except Exception as exc:  # noqa: BLE001 - reported, not fatal
            log.warning("run_delete_failed", run_id=run_id, error=str(exc)[:200])
    if (forgotten := await forget_quietly(run_id)) is not None and forgotten.semantic:
        removed.append("its support for facts in memory")
    try:
        if await (await get_case_store()).remove_investigation(run_id):
            removed.append(f"its place in {record.case_id or 'its case'}")
    except Exception as exc:  # noqa: BLE001
        log.warning("case_unlink_failed", run_id=run_id, error=str(exc)[:200])
    await audit("mission.deleted", actor=actor, target=run_id, removed=removed)
    return DeletionReport(deleted=[run_id], removed=removed)


async def delete_all_investigations(*, actor: str) -> DeletionReport:
    """Every finished investigation. Running ones are skipped and named."""
    report = DeletionReport()
    for record in get_registry().records():
        if not record.is_finished():
            report.skipped.append(f"{record.run_id} (still running)")
            continue
        one = await delete_investigation(record.run_id, actor=actor)
        report.deleted += one.deleted
    report.removed = ["each investigation, its archive, recordings, stored run and memory support"]
    await audit("missions.deleted", actor=actor, target="missions:all", deleted=len(report.deleted))
    return report


async def delete_case(case_id: str, *, actor: str) -> DeletionReport:
    """A case and every investigation in it. Its evidence stays in the Evidence Locker."""
    cases = await get_case_store()
    if await cases.get(case_id) is None:
        raise ApiError(
            "CASE_NOT_FOUND", f"no case {case_id}", status_code=status.HTTP_404_NOT_FOUND
        )
    report = DeletionReport()
    for investigation in await cases.investigations(case_id):
        record = get_registry().get(investigation.run_id)
        if record is not None and not record.is_finished():
            raise ApiError(
                "MISSION_RUNNING",
                f"{investigation.run_id} in this case is still running; cancel it first",
                status_code=status.HTTP_409_CONFLICT,
            )
    for investigation in await cases.investigations(case_id):
        if get_registry().get(investigation.run_id) is not None:
            one = await delete_investigation(investigation.run_id, actor=actor)
            report.deleted += one.deleted
    links = len(await cases.evidence(case_id))
    await cases.delete(case_id)
    report.deleted.insert(0, case_id)
    report.removed = [
        "the case",
        f"{len(report.deleted) - 1} investigation(s), each everywhere it was held",
        f"the case's links to {links} evidence item(s)",
    ]
    report.kept = [*KEPT, "the evidence items themselves, in the Evidence Locker"]
    await audit("case.deleted", actor=actor, target=case_id, removed=report.removed)
    return report
