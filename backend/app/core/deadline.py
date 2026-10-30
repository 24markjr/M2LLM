"""One deadline for a whole run (demo readiness, after a 12-file run sat in Executing for 14 min).

`Settings.run_wallclock_limit_s` was enforced only inside the execution engine, between tasks, and
each engine started its own clock - so the knowledge build before it, the replanning iterations
after it and the competing explanations could each run past the limit. A mission now sets one
deadline when it starts; every stage that loops reads it:

- the knowledge build stops sending chunks once its share of the time is spent (the rest counted
  as skipped, never silently empty);
- each execution engine's wall-clock budget is what is left of the run's;
- the replanning loop stops before another iteration when the time is spent
  (`BUDGET_EXHAUSTED`), and the run goes straight to verifying and reporting what it has;
- the optional competing-explanations step is skipped when little time is left.

A run therefore always finishes, with what it established and a record of what it did not reach.
Held in a context variable: the mission's task and everything it awaits see it; nothing else does.
"""

from __future__ import annotations

import time
from contextvars import ContextVar

_deadline: ContextVar[tuple[float, float] | None] = ContextVar("run_deadline", default=None)


def start(limit_s: float) -> None:
    """Set the run's deadline: `limit_s` seconds from now."""
    now = time.monotonic()
    _deadline.set((now, now + limit_s))


def clear() -> None:
    _deadline.set(None)


def remaining() -> float | None:
    """Seconds left for the run, or None outside a run."""
    found = _deadline.get()
    return None if found is None else max(0.0, found[1] - time.monotonic())


def used_share() -> float:
    """The share of the run's time already spent, 0.0 outside a run."""
    found = _deadline.get()
    if found is None:
        return 0.0
    started, ends = found
    return min(1.0, (time.monotonic() - started) / max(ends - started, 1e-6))


def past(share: float = 1.0) -> bool:
    """Whether at least `share` of the run's time has been spent."""
    return used_share() >= share
