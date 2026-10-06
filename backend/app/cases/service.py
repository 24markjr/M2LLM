"""Opening cases, filing investigations and evidence in them, counting what they hold (Phase 44).

Counters are computed from what a case holds - its investigations' recorded outcomes, its evidence
and that evidence's integrity - never stored as numbers that could drift from their source.

Like the Evidence Locker: Postgres when the database answers, memory otherwise (named), and filing
never fails the upload or mission it files (invariant 10).
"""

from __future__ import annotations

from app.cases.store import CaseStore, MemoryCaseStore
from app.core.logging import get_logger
from app.schemas.case import Case, CaseCounters, CaseEvidence, CaseInvestigation, CaseStatus
from app.schemas.common import utcnow
from app.schemas.evidence_locker import IntegrityStatus

log = get_logger(__name__)

_memory_store = MemoryCaseStore()
# Probed once per process; tests set it False (tests/conftest.py).
_database: bool | None = None


def reset_case_store_probe() -> None:
    global _database
    _database = None


async def get_case_store() -> CaseStore:
    global _database
    if _database is None:
        from app.database.session import database_available

        _database = await database_available()
    if _database:
        from app.database.case_store import PgCaseStore

        return PgCaseStore()
    return _memory_store


async def file_evidence(case_id: str, evidence_ids: list[str], *, actor: str = "system") -> int:
    """Put evidence items in a case. Never raises; returns how many were new to it."""
    added = 0
    try:
        store = await get_case_store()
        for evidence_id in dict.fromkeys(e for e in evidence_ids if e):
            if await store.add_evidence(
                CaseEvidence(case_id=case_id, evidence_id=evidence_id, added_by=actor)
            ):
                added += 1
    except Exception as exc:  # noqa: BLE001 - filing never fails the work it files
        log.warning("case_evidence_not_filed", case_id=case_id, error=str(exc))
    return added


async def file_investigation(investigation: CaseInvestigation) -> None:
    """Record (or update) a mission in its case. Never raises."""
    try:
        await (await get_case_store()).save_investigation(investigation)
    except Exception as exc:  # noqa: BLE001
        log.warning("case_investigation_not_filed", run_id=investigation.run_id, error=str(exc))


async def counters(store: CaseStore, case: Case, running: set[str]) -> CaseCounters:
    """What a case holds, counted now. `running` is the run ids still in progress."""
    from app.evidence.service import get_locker

    investigations = await store.investigations(case.case_id)
    held = await store.evidence(case.case_id)
    failed = 0
    if held:
        locker = await get_locker()
        for link in held:
            item = await locker.get(link.evidence_id)
            if item is not None and item.integrity is IntegrityStatus.FAILED:
                failed += 1
    return CaseCounters(
        investigations=len(investigations),
        running=sum(1 for i in investigations if i.run_id in running),
        evidence=len(held),
        failed_integrity=failed,
        findings=sum(i.findings for i in investigations),
        verified=sum(i.verified for i in investigations),
        contradictions=sum(i.contradictions for i in investigations),
        open_gaps=sum(i.open_gaps for i in investigations),
    )


async def start_investigating(case: Case) -> None:
    """An open case becomes INVESTIGATING when its first investigation starts. Never raises."""
    if case.status is not CaseStatus.OPEN:
        return
    try:
        await (await get_case_store()).update(case.case_id, status=CaseStatus.INVESTIGATING)
    except Exception as exc:  # noqa: BLE001
        log.warning("case_status_not_updated", case_id=case.case_id, error=str(exc))


def this_year() -> int:
    return utcnow().year
