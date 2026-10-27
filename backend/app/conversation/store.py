"""A case's thread, kept as one file in the runs volume (v4 Phase 3).

Beside the run archives, so the same volume, backup and redeploy keep it, and in a folder per
organisation (Phase 1c), so a case id can never reach another customer's thread. Written whole after
each turn: a thread is read whole to answer, and a few hundred turns is a small file.
"""

from __future__ import annotations

import asyncio
import re
from pathlib import Path

from app.auth.tenancy import current_org
from app.conversation.models import Thread
from app.core.config import get_settings
from app.schemas.case import CASE_ID

_locks: dict[str, asyncio.Lock] = {}


def _path(case_id: str) -> Path:
    if not re.fullmatch(CASE_ID, case_id):
        raise ValueError(f"not a case id: {case_id!r}")
    return get_settings().agent_dir / "runs" / "conversations" / current_org() / f"{case_id}.json"


def lock(case_id: str) -> asyncio.Lock:
    """One turn at a time per thread: two at once would each append to a copy and lose the other."""
    return _locks.setdefault(f"{current_org()}/{case_id}", asyncio.Lock())


def load(case_id: str) -> Thread:
    path = _path(case_id)
    if not path.is_file():
        return Thread(case_id=case_id)
    return Thread.model_validate_json(path.read_text(encoding="utf-8"))


def save(thread: Thread) -> None:
    path = _path(thread.case_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(".part")
    temporary.write_text(thread.model_dump_json(indent=1), encoding="utf-8")
    temporary.replace(path)
