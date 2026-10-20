"""Recordings and evaluation reports — the two things the UI reads that are not a live run.

Both are files on disk written by the system itself. Neither route computes anything: a number
the UI charts must be a number a run produced, and a route that derived one here would be a
second place where metrics come from.
"""

from __future__ import annotations

from typing import Any, Literal

from fastapi import APIRouter, Query, status

from app.api.errors import ApiError
from app.api.recording import (
    delete_recording,
    delete_recordings,
    list_recordings,
    load_recording,
)
from app.core.logging import get_logger
from app.evaluation.benchmark import BenchmarkReport, newest_report
from app.evaluation.quality import QualitySummary, quality_summary
from app.evaluation.report import LOWER_IS_BETTER, EvalReport
from app.evaluation.runner import reports_dir
from app.review.service import audit
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
    # Phase U1: what it found, its case, and why it is hidden from the default list ("" = shown).
    findings: int = 0
    verified: int = 0
    case_id: str = ""
    hidden: str = ""


class DeletedRecordings(JarvisModel):
    deleted: int
    # Committed recordings are part of the repository and are never deleted from the console.
    kept: int


@router.get("/recordings", response_model=list[RecordingSummary])
async def get_recordings(
    include_hidden: bool = Query(default=False),
) -> list[RecordingSummary]:
    """Recorded runs available to replay, newest first. Failed runs that found nothing, and second
    copies of a run, are left out unless `include_hidden`; each says why."""
    return [RecordingSummary(**row) for row in list_recordings(include_hidden=include_hidden)]


@router.delete("/recordings/{name}", status_code=status.HTTP_204_NO_CONTENT)
async def remove_recording(name: str) -> None:
    """Delete one local recording. The investigation it replays is not touched."""
    outcome = delete_recording(name)
    if outcome == "missing":
        raise ApiError(
            "RECORDING_NOT_FOUND",
            f"no recording named {name}",
            status_code=status.HTTP_404_NOT_FOUND,
        )
    if outcome == "kept":
        raise ApiError(
            "RECORDING_KEPT",
            f"{name} is committed to the repository; remove it with git, not from the console",
            status_code=status.HTTP_409_CONFLICT,
        )
    await audit("recording.deleted", target=name)


@router.delete("/recordings", response_model=DeletedRecordings)
async def remove_recordings(
    scope: Literal["hidden", "all"] = Query(default="hidden"),
    confirm: str = Query(default=""),
) -> DeletedRecordings:
    """Delete the hidden recordings, or all local ones. `confirm=delete` is required, so a stray
    request cannot empty the history."""
    if confirm != "delete":
        raise ApiError(
            "CONFIRMATION_REQUIRED",
            "deleting recordings needs confirm=delete",
            status_code=status.HTTP_400_BAD_REQUEST,
        )
    deleted, kept = delete_recordings(hidden_only=scope == "hidden")
    await audit("recordings.deleted", target=f"recordings:{scope}", deleted=deleted, kept=kept)
    return DeletedRecordings(deleted=deleted, kept=kept)


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


@router.get("/evaluation/quality", response_model=QualitySummary)
async def get_evaluation_quality() -> QualitySummary:
    """One quality figure with its formula, its components (each naming the report and scenarios it
    came from), the figures by category, and the agent-quality trend (Phase 54)."""
    return quality_summary()


@router.get("/evaluation/benchmark", response_model=BenchmarkReport)
async def get_evaluation_benchmark() -> BenchmarkReport:
    """The newest benchmark (Phase B1): JARVIS, the plain model and any frontier model, scored
    against the answer key by the same deterministic judge. Produced locally and committed."""
    report = newest_report()
    if report is None:
        raise ApiError(
            "BENCHMARK_NOT_RUN",
            "no benchmark yet: run python -m app.evaluation.benchmark",
            status_code=status.HTTP_404_NOT_FOUND,
        )
    return report


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
