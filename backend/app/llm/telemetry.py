"""LLM call telemetry.

Repair counts, latency and token usage are first-class results, not debug output. A model
that needs two repair passes per call is a different engineering proposition from one that
needs none, even at identical final accuracy — and Experiment 001 compares exactly that.

Telemetry reaches the run timeline as `LLM_CALL_COMPLETED` events. What it deliberately does
**not** carry is prompt or completion text: that is model deliberation, and invariant #3
keeps it out of the record. Counts and timings, never content.
"""

from __future__ import annotations

from typing import Any

from pydantic import Field

from app.core.logging import get_logger
from app.schemas.common import JarvisModel
from app.schemas.event import EventType

log = get_logger(__name__)


class LLMCallRecord(JarvisModel):
    """One model call. Counts and timings only."""

    role: str
    model: str
    latency_ms: int = Field(default=0, ge=0)
    prompt_tokens: int = Field(default=0, ge=0)
    completion_tokens: int = Field(default=0, ge=0)
    # 0 on the first attempt; >0 means the repair loop ran.
    repair_attempt: int = Field(default=0, ge=0)
    ok: bool = True
    schema_name: str = ""

    @property
    def needed_repair(self) -> bool:
        return self.repair_attempt > 0


class TelemetryCollector:
    """In-process aggregate, for the evaluation harness and quick inspection."""

    def __init__(self) -> None:
        self.records: list[LLMCallRecord] = []

    def add(self, record: LLMCallRecord) -> None:
        self.records.append(record)

    @property
    def total_calls(self) -> int:
        return len(self.records)

    @property
    def repair_rate(self) -> float:
        """Share of successful results that required at least one repair.

        A Phase 20 metric: the honest measure of how well a given model handles strict
        structured output.
        """
        successes = [r for r in self.records if r.ok]
        if not successes:
            return 0.0
        return sum(1 for r in successes if r.needed_repair) / len(successes)

    @property
    def total_latency_ms(self) -> int:
        return sum(r.latency_ms for r in self.records)

    @property
    def total_tokens(self) -> int:
        return sum(r.prompt_tokens + r.completion_tokens for r in self.records)

    def clear(self) -> None:
        self.records.clear()


_collector = TelemetryCollector()


def get_collector() -> TelemetryCollector:
    return _collector


async def record_call(record: LLMCallRecord, *, emit: Any | None = None) -> None:
    """Record a call locally, and on the run timeline when an emitter is supplied.

    `emit` is typed loosely to keep `app.llm` from importing the event layer for what is an
    optional hook. Engines pass their `RunEventEmitter`; unit tests pass nothing.
    """
    _collector.add(record)

    if record.needed_repair or not record.ok:
        log.info(
            "llm_call",
            role=record.role,
            schema=record.schema_name,
            ok=record.ok,
            repair_attempt=record.repair_attempt,
            latency_ms=record.latency_ms,
        )

    if emit is None:
        return

    emit_fn = getattr(emit, "emit", None)
    if emit_fn is None:
        return

    await emit_fn(
        EventType.LLM_CALL_COMPLETED,
        payload={
            "role": record.role,
            "model": record.model,
            "schema": record.schema_name,
            "ok": record.ok,
            "repair_attempt": record.repair_attempt,
            "latency_ms": record.latency_ms,
            "prompt_tokens": record.prompt_tokens,
            "completion_tokens": record.completion_tokens,
        },
    )
