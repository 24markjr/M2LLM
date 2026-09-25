"""Recordings and evaluation reports — the two things the UI reads that are not a live run.

Both are files on disk written by the system itself. Neither route computes anything: a number
the UI charts must be a number a run produced, and a route that derived one here would be a
second place where metrics come from.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, status

from app.api.errors import ApiError
from app.api.recording import list_recordings, load_recording
from app.core.logging import get_logger
from app.evaluation.report import LOWER_IS_BETTER, EvalReport
from app.evaluation.runner import reports_dir
from app.schemas.common import JarvisModel

log = get_logger(__name__)
router = APIRouter(tags=["replay"])


class RecordingSummary(JarvisModel):
    run_id: str
    file: str
    objective: str
    model: str
    outcome: str
    recorded_at: str
    event_count: int
    duration_ms: int
    # Whether this recording is committed to the repo rather than local scratch.
    committed: bool


@router.get("/recordings", response_model=list[RecordingSummary])
async def get_recordings() -> list[RecordingSummary]:
    """Recorded runs available to replay, newest first."""
    return [RecordingSummary(**row) for row in list_recordings()]


@router.get("/recordings/{name}")
async def get_recording(name: str) -> dict[str, Any]:
    """One recording: its events and the run's final state.

    Served whole. A replay needs every event in order, and paginating them would make the
    client reassemble a file that is already a single document.
    """
    recording = load_recording(name)
    if recording is None:
        raise ApiError(
            "RECORDING_NOT_FOUND",
            f"no recording named {name}",
            status_code=status.HTTP_404_NOT_FOUND,
        )
    return recording


class MetricPoint(JarvisModel):
    """One suite run, as a point on a trend line."""

    generated_at: str
    model: str
    config_hash: str
    prompt_versions: dict[str, int]
    suite: str
    metrics: dict[str, float]
    confabulations: int
    blind_spots: int
    # Reports only compare within a comparability key; see the evaluation docs.
    comparable_key: str


@router.get("/evaluation/reports", response_model=list[MetricPoint])
async def get_evaluation_reports() -> list[MetricPoint]:
    """Every committed evaluation report, oldest first, as trend points.

    Oldest first because this is charted as a series and a series reads left to right.

    The UI must not join points across a change of `comparable_key`. Two reports produced with
    different models or prompt versions describe different systems, and a line drawn between
    them shows a regression or an improvement that never happened.
    """
    directory = reports_dir()
    if not directory.is_dir():
        return []

    points: list[MetricPoint] = []
    for path in sorted(directory.glob("*.json")):
        try:
            report = EvalReport.model_validate_json(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            # Unreadable or not a valid report. Skipped and logged, never silently treated as
            # empty - a gap in a trend line is a fact about the data, not a zero.
            log.warning("eval_report_unreadable", path=str(path))
            continue

        points.append(
            MetricPoint(
                generated_at=report.generated_at.isoformat(),
                model=report.model,
                config_hash=report.config_hash,
                prompt_versions=dict(report.prompt_versions),
                suite=report.suite,
                metrics={name: float(value) for name, value in report.aggregate.as_dict().items()},
                confabulations=len(report.confabulations),
                blind_spots=len(report.blind_spots),
                comparable_key=report.comparable_key,
            )
        )

    return points


@router.get("/evaluation/directions", response_model=dict[str, str])
async def get_metric_directions() -> dict[str, str]:
    """Which way is better for each metric.

    Served rather than hardcoded in the UI: the direction of a metric is a property of the
    metric, and a chart that colours a rising `unsupported_claim_rate` green because the
    frontend held a stale copy of this list would be worse than no colour at all.
    """
    from app.evaluation.metrics import MetricSet

    return {
        name: "lower" if name in LOWER_IS_BETTER else "higher" for name in MetricSet.model_fields
    }
