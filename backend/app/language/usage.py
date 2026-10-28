"""What the language engines were asked to do, per organisation (v4 Phases 7-8).

One JSON line per call - engine, task, languages, how much, how long, whether it worked and whether
it was a fallback - appended to `.agent/runs/language-usage/<org>.jsonl`. Operations reads it: calls
and volume by engine, failures, and fallbacks from Bhashini to the open-source engine. Writing never
fails the caller; a usage line lost is better than a translation lost.
"""

from __future__ import annotations

import json
from datetime import timedelta
from pathlib import Path

from pydantic import Field

from app.auth.tenancy import current_org
from app.core.config import get_settings
from app.core.logging import get_logger
from app.schemas.common import JarvisModel, utcnow

log = get_logger(__name__)


def _path() -> Path:
    return get_settings().agent_dir / "runs" / "language-usage" / f"{current_org()}.jsonl"


def record_usage(
    *,
    engine: str,
    task: str,
    source: str,
    target: str,
    amount: int,
    unit: str,
    ms: int,
    ok: bool,
    fallback: bool = False,
) -> None:
    line = {
        "at": utcnow().isoformat(),
        "engine": engine,
        "task": task,
        "source": source,
        "target": target,
        "amount": amount,
        "unit": unit,
        "ms": ms,
        "ok": ok,
        "fallback": fallback,
    }
    try:
        path = _path()
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(line) + "\n")
    except OSError as exc:
        log.warning("language_usage_unwritten", error=str(exc))


class EngineUsage(JarvisModel):
    engine: str
    calls: int = 0
    failed: int = 0
    fallbacks: int = 0
    characters: int = 0
    seconds: float = 0.0


class LanguageUsage(JarvisModel):
    days: int
    engines: list[EngineUsage] = Field(default_factory=list)
    by_task: dict[str, int] = Field(default_factory=dict)


def usage_summary(days: int = 30) -> LanguageUsage:
    since = (utcnow() - timedelta(days=days)).isoformat()
    engines: dict[str, EngineUsage] = {}
    by_task: dict[str, int] = {}
    path = _path()
    lines = path.read_text(encoding="utf-8").splitlines() if path.is_file() else []
    for raw in lines:
        try:
            row = json.loads(raw)
        except ValueError:
            continue
        if str(row.get("at", "")) < since:
            continue
        name = str(row.get("engine", "?"))
        usage = engines.setdefault(name, EngineUsage(engine=name))
        usage.calls += 1
        usage.failed += not row.get("ok", True)
        usage.fallbacks += bool(row.get("fallback"))
        if row.get("unit") == "characters":
            usage.characters += int(row.get("amount", 0) or 0)
        usage.seconds = round(usage.seconds + int(row.get("ms", 0) or 0) / 1000, 2)
        task = str(row.get("task", "?"))
        by_task[task] = by_task.get(task, 0) + 1
    return LanguageUsage(
        days=days, engines=sorted(engines.values(), key=lambda e: e.engine), by_task=by_task
    )
