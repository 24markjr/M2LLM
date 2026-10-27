"""Per-account request limits (v4 Phase 1): one account, or a stolen session, cannot flood the API.

A sliding minute per signed-in user, in this process: the deployment is one backend process, and
the limit protects it rather than metering a customer. Generous enough that the console - which
polls a running investigation and streams its events - never meets it; a script hammering the
API does. Sign-in has its own, stricter throttle (`service.throttled`), and a model that is busy
already refuses new missions with 429 `AT_CAPACITY`.
"""

from __future__ import annotations

import time
from collections import deque

REQUESTS_PER_MINUTE = 600
WRITES_PER_MINUTE = 120
WINDOW_S = 60.0

_all: dict[str, deque[float]] = {}
_writes: dict[str, deque[float]] = {}


def _over(log: dict[str, deque[float]], user_id: str, limit: int, now: float) -> bool:
    times = log.setdefault(user_id, deque())
    while times and now - times[0] >= WINDOW_S:
        times.popleft()
    if len(times) >= limit:
        return True
    times.append(now)
    return False


def over_limit(user_id: str, write: bool, now: float | None = None) -> bool:
    """Whether this request is one too many; counted when it is not."""
    now = time.monotonic() if now is None else now
    if write and _over(_writes, user_id, WRITES_PER_MINUTE, now):
        return True
    return _over(_all, user_id, REQUESTS_PER_MINUTE, now)


def reset() -> None:
    _all.clear()
    _writes.clear()
