"""The run archive: a finished mission, kept so it survives a restart (Phase U1).

Until U1 the registry was memory alone. Runs were written to Postgres (`persistence.py`), but
nothing read them back, so after a restart the Missions list was empty while a case still listed its
investigations - two views of the same work disagreeing.

An archive is the mission record as the API serves it: the result, the events, the evidence it read
and the text it read it as, its case, its knowledge graph, its challenges. Restoring one gives back
the same record, so every route - findings, the report, the graph, a challenge - answers for a run
from last week exactly as for one from a minute ago. It is a file per run under `.agent/runs/`
(gitignored), so it needs no database: the console without Postgres keeps its history too.

A recording (`recording.py`) is a different thing: a replay of the events. Deleting a recording
leaves the investigation; deleting an investigation removes both.
"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any

from pydantic import Field

from app.core.config import get_settings
from app.core.logging import get_logger
from app.intelligence.challenge import ChallengeResult
from app.orchestration.mission import MissionResult, MissionStatus, Stage
from app.schemas.common import JarvisModel
from app.schemas.event import ExecutionEvent
from app.schemas.objective import Objective

if TYPE_CHECKING:
    from app.api.registry import MissionRecord

log = get_logger(__name__)

RUN_ID = r"^run_[0-9a-f]{12}$"


class RunArchive(JarvisModel):
    version: int = 1
    run_id: str = Field(pattern=RUN_ID)
    objective: Objective
    documents: list[str] = Field(default_factory=list)
    status: MissionStatus
    stage: Stage = Stage.DONE
    created_at: datetime
    started_at: datetime | None = None
    finished_at: datetime | None = None
    result: MissionResult | None = None
    events: list[ExecutionEvent] = Field(default_factory=list)
    evidence: dict[str, str] = Field(default_factory=dict)
    excluded: dict[str, str] = Field(default_factory=dict)
    authority: dict[str, str] = Field(default_factory=dict)
    texts: dict[str, str] = Field(default_factory=dict)
    page_starts: dict[str, list[int]] = Field(default_factory=dict)
    case_id: str = ""
    knowledge_view: dict[str, Any] | None = None
    knowledge_timeline: list[dict[str, Any]] | None = None
    challenges: dict[str, ChallengeResult] = Field(default_factory=dict)


def archives_dir() -> Path:
    return get_settings().agent_dir / "runs"


def path_for(run_id: str) -> Path:
    return archives_dir() / f"{run_id}.json"


def write_archive(record: MissionRecord) -> Path | None:
    """Write (or rewrite) a finished run's archive. Never raises: the run is already over."""
    if not record.is_finished():
        return None
    try:
        archive = RunArchive(
            run_id=record.run_id,
            objective=record.objective,
            documents=list(record.documents),
            status=record.status,
            stage=record.stage,
            created_at=record.created_at,
            started_at=record.started_at,
            finished_at=record.finished_at,
            result=record.result,
            events=list(record.events),
            evidence=dict(record.evidence),
            excluded=dict(record.excluded),
            authority=dict(record.authority),
            texts=dict(record.texts),
            page_starts=dict(record.page_starts),
            case_id=record.case_id,
            knowledge_view=dict(record.knowledge_view) if record.knowledge_view else None,
            knowledge_timeline=list(record.knowledge_timeline or []) or None,
            challenges=dict(record.challenges),
        )
        directory = archives_dir()
        directory.mkdir(parents=True, exist_ok=True)
        target = path_for(record.run_id)
        partial = target.with_suffix(".part")
        partial.write_text(archive.model_dump_json(), encoding="utf-8")
        partial.replace(target)  # a crash mid-write never leaves half an archive
        return target
    except Exception:  # losing the archive must never fail the run
        log.exception("archive_failed", run_id=record.run_id)
        return None


def read_archives() -> list[RunArchive]:
    """Every readable archive, oldest first. An unreadable one is logged and skipped."""
    directory = archives_dir()
    if not directory.is_dir():
        return []
    archives: list[RunArchive] = []
    for path in directory.glob("run_*.json"):
        try:
            archives.append(RunArchive.model_validate_json(path.read_text(encoding="utf-8")))
        except (OSError, ValueError) as exc:
            log.warning("archive_unreadable", path=path.name, error=str(exc)[:200])
    return sorted(archives, key=lambda a: a.created_at)


def delete_archive(run_id: str) -> bool:
    target = path_for(run_id)
    if target.parent != archives_dir() or not target.is_file():
        return False
    target.unlink()
    return True


def as_json(archive: RunArchive) -> dict[str, Any]:
    loaded: dict[str, Any] = json.loads(archive.model_dump_json())
    return loaded
