"""What each investigation took, and what it cost (v4 Phase 8).

Computed from the run's own record - its timestamps and the `LLM_CALL_COMPLETED` events every model
call puts on its timeline - so the numbers cannot drift from what happened. Nothing is sampled.

Cost is an estimate at configured rates, and says so: the model's working time (the sum of its call
latencies) at the GPU's hourly rate, plus the run's wall time at the server's rate shared by the
runs that can go at once. Tokens are counted and shown, but a self-hosted model is paid for by
the hour, not by the token.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from statistics import median

from pydantic import Field

from app.api.registry import MissionRecord
from app.core.config import get_settings
from app.orchestration.mission import MissionStatus
from app.schemas.common import JarvisModel, utcnow
from app.schemas.event import EventType


class RunMetrics(JarvisModel):
    run_id: str
    status: str
    created_at: datetime
    queue_wait_s: float = 0.0
    duration_s: float = 0.0
    llm_calls: int = 0
    failed_calls: int = 0
    repairs: int = 0
    prompt_tokens: int = 0
    completion_tokens: int = 0
    model_seconds: float = 0.0
    cost_inr: float = 0.0
    error: str = ""


class Summary(JarvisModel):
    days: int
    investigations: int = 0
    completed: int = 0
    failed: int = 0
    cancelled: int = 0
    running: int = 0
    waiting: int = 0
    error_rate: float = 0.0
    duration_p50_s: float = 0.0
    duration_p95_s: float = 0.0
    queue_wait_p50_s: float = 0.0
    llm_calls: int = 0
    tokens: int = 0
    cost_total_inr: float = 0.0
    cost_per_investigation_inr: float = 0.0
    rates: dict[str, float] = Field(default_factory=dict)
    by_day: list[dict[str, float | str]] = Field(default_factory=list)
    recent_errors: list[RunMetrics] = Field(default_factory=list)


def run_metrics(record: MissionRecord) -> RunMetrics:
    settings = get_settings()
    metrics = RunMetrics(
        run_id=record.run_id, status=record.status.value, created_at=record.created_at
    )
    if record.started_at is not None:
        metrics.queue_wait_s = round((record.started_at - record.created_at).total_seconds(), 2)
        end = record.finished_at or utcnow()
        metrics.duration_s = round((end - record.started_at).total_seconds(), 2)
    latency_ms = 0
    for event in record.events:
        if event.event_type is not EventType.LLM_CALL_COMPLETED:
            continue
        payload = event.payload
        metrics.llm_calls += 1
        metrics.failed_calls += not payload.get("ok", True)
        metrics.repairs += int(payload.get("repair_attempt", 0) or 0) > 0
        metrics.prompt_tokens += int(payload.get("prompt_tokens", 0) or 0)
        metrics.completion_tokens += int(payload.get("completion_tokens", 0) or 0)
        latency_ms += int(payload.get("latency_ms", 0) or 0)
    metrics.model_seconds = round(latency_ms / 1000, 2)
    metrics.cost_inr = round(
        metrics.model_seconds / 3600 * settings.gpu_cost_per_hour_inr
        + metrics.duration_s
        / 3600
        * settings.server_cost_per_hour_inr
        / settings.max_concurrent_runs,
        4,
    )
    if record.status is MissionStatus.FAILED and record.result is not None:
        metrics.error = f"{record.result.error_code}: {record.result.error_message}"[:300]
    return metrics


def _percentile(values: list[float], share: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    return round(ordered[min(len(ordered) - 1, int(share * len(ordered)))], 2)


def summarise(
    records: list[MissionRecord], *, days: int, running: int = 0, waiting: int = 0
) -> Summary:
    """The organisation's investigations of the last `days` days, in one view."""
    settings = get_settings()
    since = utcnow() - timedelta(days=days)
    runs = [run_metrics(r) for r in records if r.created_at >= since]
    finished = [m for m in runs if m.status in {"COMPLETED", "FAILED", "CANCELLED"}]
    completed = [m for m in runs if m.status == "COMPLETED"]
    failed = [m for m in runs if m.status == "FAILED"]
    days_seen: dict[str, list[RunMetrics]] = {}
    for m in runs:
        days_seen.setdefault(m.created_at.date().isoformat(), []).append(m)
    total_cost = round(sum(m.cost_inr for m in runs), 2)
    return Summary(
        days=days,
        investigations=len(runs),
        completed=len(completed),
        failed=len(failed),
        cancelled=sum(1 for m in runs if m.status == "CANCELLED"),
        running=running,
        waiting=waiting,
        error_rate=round(len(failed) / len(finished), 3) if finished else 0.0,
        duration_p50_s=round(median([m.duration_s for m in completed]), 2) if completed else 0.0,
        duration_p95_s=_percentile([m.duration_s for m in completed], 0.95),
        queue_wait_p50_s=round(median([m.queue_wait_s for m in runs]), 2) if runs else 0.0,
        llm_calls=sum(m.llm_calls for m in runs),
        tokens=sum(m.prompt_tokens + m.completion_tokens for m in runs),
        cost_total_inr=total_cost,
        cost_per_investigation_inr=round(total_cost / len(completed), 2) if completed else 0.0,
        rates={
            "gpu_per_hour_inr": settings.gpu_cost_per_hour_inr,
            "server_per_hour_inr": settings.server_cost_per_hour_inr,
        },
        by_day=[
            {
                "day": day,
                "investigations": len(items),
                "failed": sum(1 for m in items if m.status == "FAILED"),
                "cost_inr": round(sum(m.cost_inr for m in items), 2),
            }
            for day, items in sorted(days_seen.items())
        ],
        recent_errors=sorted(failed, key=lambda m: m.created_at, reverse=True)[:10],
    )
