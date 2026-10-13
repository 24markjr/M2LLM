"""Recording a finished mission so it can be replayed.

**Why this exists.** Local inference on laptop hardware stalls sometimes, and a demo should not
depend on a model behaving on the day. A recorded run replays at speed and looks exactly like a
live one — which is only honest if the UI says it is a replay, and it does.

**A recording is never authored.** Everything written here came out of a real run. A
hand-written trace is evidence of behaviour that never happened (invariant 5), and the cost of
that is not a bad demo, it is a false claim.

Recordings land in `.agent/traces/` as `<run_id>.local.json` and are gitignored. A recording
worth keeping is renamed deliberately, which is what makes a committed one a considered act
rather than an accident of whatever ran last.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import TYPE_CHECKING, Any

from app.core.config import get_settings
from app.core.logging import get_logger
from app.schemas.event import ExecutionTrace

if TYPE_CHECKING:
    from app.api.registry import MissionRecord

log = get_logger(__name__)

SCRATCH_SUFFIX = ".local.json"


def recordings_dir() -> Path:
    return get_settings().agent_dir / "traces"


def write_recording(record: MissionRecord) -> Path | None:
    """Write a finished mission's events and final state. Returns None if nothing to record.

    Never raises. A failure to record is a lost demo aid, not a reason to fail a run that
    already produced its findings - the caller is a `finally` block on the mission task.
    """
    if not record.events:
        return None

    try:
        trace = ExecutionTrace(
            run_id=record.run_id,
            objective=record.objective.text or "(objective not recorded)",
            model=get_settings().ollama_model,
            outcome=record.status.value,
            events=list(record.events),
            snapshot=_snapshot(record),
        )
        directory = recordings_dir()
        directory.mkdir(parents=True, exist_ok=True)
        path = directory / f"{record.run_id}{SCRATCH_SUFFIX}"
        path.write_text(json.dumps(trace.model_dump(mode="json"), indent=2), encoding="utf-8")
        log.info("recording_written", run_id=record.run_id, events=len(record.events))
        return path
    except Exception:  # the run is already over; losing the recording must not raise
        log.exception("recording_failed", run_id=record.run_id)
        return None


def _snapshot(record: MissionRecord) -> dict[str, Any]:
    """The run's final state, in the same shape the API serves it.

    Built through the route shapers rather than by hand, so a replay is fed byte-identical
    payloads to a live view. If these ever diverge, the replay stops being a faithful
    rendering of the run and starts being a second implementation of one.
    """
    from app.api.v1.missions import snapshot_payloads

    return snapshot_payloads(record)


# Why a recording is hidden from the default list (Phase U1). Hidden, never deleted on its own:
# deleting is the person's decision.
HIDDEN_EMPTY = "the run failed or was cancelled before it found anything"
HIDDEN_DUPLICATE = "another file holds the same run"


def list_recordings(*, include_hidden: bool = True) -> list[dict[str, Any]]:
    """Every recording on disk, newest first, as a record: what was asked, how it ended, what it
    found, its case. A failed run with no findings, or a second file of the same run, is marked
    `hidden` with the reason, and left out unless `include_hidden`."""
    directory = recordings_dir()
    if not directory.is_dir():
        return []

    rows: list[dict[str, Any]] = []
    for path in directory.glob("*.json"):
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            log.warning("recording_unreadable", path=str(path))
            continue

        events = raw.get("events") or []
        mission = (raw.get("snapshot") or {}).get("mission") or {}
        rows.append(
            {
                "run_id": raw.get("run_id", path.stem),
                "file": path.name,
                "objective": raw.get("objective", ""),
                "model": raw.get("model", ""),
                "outcome": raw.get("outcome", ""),
                "recorded_at": raw.get("recorded_at", ""),
                "event_count": len(events),
                "duration_ms": events[-1].get("t_offset_ms", 0) if events else 0,
                "committed": not path.name.endswith(SCRATCH_SUFFIX),
                "findings": int(mission.get("finding_count", 0) or 0),
                "verified": int(mission.get("verified_count", 0) or 0),
                "case_id": str(mission.get("case_id", "") or ""),
                "hidden": "",
            }
        )

    rows.sort(key=lambda row: str(row["recorded_at"]), reverse=True)
    # One file per run in the default list: a committed copy first, else the newest.
    seen: set[str] = set()
    for row in sorted(rows, key=lambda r: not r["committed"]):
        if row["run_id"] in seen:
            row["hidden"] = HIDDEN_DUPLICATE
        seen.add(row["run_id"])
    for row in rows:
        if not row["hidden"] and row["findings"] == 0 and row["outcome"] in ("FAILED", "CANCELLED"):
            row["hidden"] = HIDDEN_EMPTY
    return rows if include_hidden else [r for r in rows if not r["hidden"]]


def delete_recording(name: str) -> str:
    """Delete one recording: "deleted", "kept" (committed to the repository: removed with git, not
    from the console) or "missing". The name is resolved strictly inside the recordings folder."""
    directory = recordings_dir().resolve()
    candidate = (directory / Path(name).name).resolve()
    if candidate.parent != directory or not candidate.is_file():
        return "missing"
    if not candidate.name.endswith(SCRATCH_SUFFIX):
        return "kept"
    candidate.unlink()
    return "deleted"


def delete_recordings(*, hidden_only: bool) -> tuple[int, int]:
    """Delete every local recording, or only the hidden ones. Returns (deleted, kept)."""
    deleted = kept = 0
    for row in list_recordings():
        if hidden_only and not row["hidden"]:
            continue
        outcome = delete_recording(str(row["file"]))
        deleted += outcome == "deleted"
        kept += outcome == "kept"
    return deleted, kept


def load_recording(name: str) -> dict[str, Any] | None:
    """Load one recording by file name.

    The name is resolved strictly inside the recordings directory. A caller-supplied path is
    untrusted input, and `..` in a filename is the oldest way to read a file the API was never
    meant to serve.
    """
    directory = recordings_dir().resolve()
    candidate = (directory / Path(name).name).resolve()
    if candidate.parent != directory or not candidate.is_file():
        return None

    try:
        loaded = json.loads(candidate.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        log.warning("recording_unreadable", path=str(candidate))
        return None
    return loaded if isinstance(loaded, dict) else None
