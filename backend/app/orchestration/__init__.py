"""Mission orchestration — the pipeline, with nothing attached to it.

Until this package existed the only way to run a mission was `app/cli.py`, where the
sequence was interleaved with `print()`. That made the terminal the one client the engine
could have. Everything here is headless: it returns a `MissionResult` and emits events, and
a caller decides whether that becomes terminal output, an HTTP response or a live stream.
"""

from app.orchestration.mission import (
    MissionResult,
    MissionStatus,
    Stage,
    run_mission,
)

__all__ = ["MissionResult", "MissionStatus", "Stage", "run_mission"]
