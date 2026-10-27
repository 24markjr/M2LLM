"""Watch folders and scheduled re-investigation (v4 Phase 10).

A case can watch a folder: every few minutes, a file dropped there is taken in as evidence - stored
under its hash, custody first ("found in the watch folder") - copied into the organisation's uploads
under its name, and filed in the case. The case can then re-run its latest investigation with the
new files, and/or re-run it every N days whether or not anything arrived.

The folder is on the server, inside the organisation's uploads (so the same volume keeps it):
`<uploads>/watch/<case_id>/`. On-premise, point a share or a scanner at it; in the cloud, sync into
it (e.g. a mounted bucket). A file is taken once, by name and hash; a changed file under the same
name is taken again as a new version, and both are in the evidence locker.
"""

from __future__ import annotations

import asyncio
import json
import shutil
from datetime import datetime, timedelta
from pathlib import Path

from pydantic import Field

from app.auth.tenancy import current_org, uploads_dir
from app.core.config import get_settings
from app.core.logging import get_logger
from app.schemas.common import JarvisModel, utcnow

log = get_logger(__name__)

WATCH_EVERY_S = 300


class WatchSettings(JarvisModel):
    enabled: bool = False
    # Re-run the case's latest investigation, with the new files, when files arrive.
    rerun_on_new_files: bool = True
    # Re-run it every N days regardless (0: never).
    rerun_every_days: int = Field(default=0, ge=0, le=365)
    last_rerun_at: datetime | None = None
    # name -> hash of every file already taken in.
    seen: dict[str, str] = Field(default_factory=dict)


class ScanResult(JarvisModel):
    case_id: str
    folder: str
    taken: list[str] = Field(default_factory=list)
    rerun: str = ""  # the new run's id, when one was started
    reason: str = ""


def folder(case_id: str) -> Path:
    return uploads_dir() / "watch" / case_id


def _settings_path(case_id: str) -> Path:
    return get_settings().agent_dir / "runs" / "watch" / current_org() / f"{case_id}.json"


def load(case_id: str) -> WatchSettings:
    path = _settings_path(case_id)
    return (
        WatchSettings.model_validate_json(path.read_text("utf-8"))
        if path.is_file()
        else WatchSettings()
    )


def save(case_id: str, value: WatchSettings) -> WatchSettings:
    path = _settings_path(case_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(value.model_dump_json(indent=1), encoding="utf-8")
    if value.enabled:
        folder(case_id).mkdir(parents=True, exist_ok=True)
    return value


def watched_cases() -> list[str]:
    root = get_settings().agent_dir / "runs" / "watch" / current_org()
    return sorted(p.stem for p in root.glob("CASE-*.json")) if root.is_dir() else []


async def scan(case_id: str, *, actor: str = "watch-folder") -> ScanResult:
    """Take in what is new in the case's folder; re-run if the settings say so."""
    from app.cases.service import file_evidence
    from app.evidence import service as evidence
    from app.evidence import store

    config = load(case_id)
    source = folder(case_id)
    result = ScanResult(case_id=case_id, folder=str(source))
    if not config.enabled:
        result.reason = "watching is off for this case"
        return result
    source.mkdir(parents=True, exist_ok=True)
    locker = await evidence.get_locker()
    ids: list[str] = []
    for path in sorted(source.iterdir()):
        if not path.is_file() or path.name.startswith(".") or path.suffix == ".part":
            continue
        sha = await asyncio.to_thread(store.hash_file, path)
        if config.seen.get(path.name) == sha:
            continue
        target = uploads_dir() / path.name
        await asyncio.to_thread(shutil.copyfile, path, target)
        item = await evidence.intake(
            locker,
            target,
            name=path.name,
            actor=actor,
            source=f"found in the watch folder of {case_id}",
        )
        ids.append(item.evidence_id)
        config.seen[path.name] = sha
        result.taken.append(path.name)
    if ids:
        await file_evidence(case_id, ids, actor=actor)

    due = config.rerun_every_days and (
        config.last_rerun_at is None
        or utcnow() - config.last_rerun_at >= timedelta(days=config.rerun_every_days)
    )
    if (result.taken and config.rerun_on_new_files) or due:
        result.rerun = await _rerun_latest(case_id, result.taken)
        if result.rerun:
            config.last_rerun_at = utcnow()
            result.reason = (
                "new files" if result.taken else f"every {config.rerun_every_days} day(s)"
            )
    save(case_id, config)
    return result


async def _rerun_latest(case_id: str, new_files: list[str]) -> str:
    """The case's latest investigation again, with the new files added. "" when there is none."""
    from app.api.registry import get_registry
    from app.api.v1.missions import create_mission
    from app.api.v1.schemas import CreateMissionRequest
    from app.cases.service import get_case_store

    registry = get_registry()
    runs = [registry.get(i.run_id) for i in await (await get_case_store()).investigations(case_id)]
    finished = sorted(
        (r for r in runs if r is not None and r.is_finished()), key=lambda r: r.created_at
    )
    if not finished:
        return ""
    latest = finished[-1]
    detail = await create_mission(
        CreateMissionRequest(
            objective=latest.objective.text,
            documents=list(dict.fromkeys([*latest.documents, *new_files]))[:64],
            case_id=case_id,
            mode=latest.objective.mode,
        )
    )
    return detail.run_id


async def watch_sweeps() -> None:
    """Scan every watched case of every organisation, every few minutes, while the server runs."""
    from app.auth.service import get_auth_store
    from app.auth.tenancy import use_org

    while True:
        await asyncio.sleep(WATCH_EVERY_S)
        try:
            orgs = sorted({u.org_id for u in await (await get_auth_store()).users()})
            for org in orgs:
                with use_org(org):
                    for case_id in watched_cases():
                        done = await scan(case_id)
                        if done.taken or done.rerun:
                            log.info(
                                "watch_scan",
                                org=org,
                                case=case_id,
                                taken=done.taken,
                                rerun=done.rerun,
                            )
        except Exception:
            log.exception("watch_sweep_failed")


def describe(case_id: str) -> dict[str, object]:
    config = load(case_id)
    return {**json.loads(config.model_dump_json()), "folder": str(folder(case_id))}
