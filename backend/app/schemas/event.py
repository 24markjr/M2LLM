"""Execution events: the run timeline.

Invariant #4 — a run must be fully reconstructable from its event log alone. That is a
strong claim, and it is what makes the trace a genuine artifact rather than decorative
logging: the UI, the demo replay and the evaluation harness all read the same events.

Invariant #3 — events carry **operational** facts only. Which task was selected, which tool
ran, what evidence was retrieved, what verification concluded, why the plan changed. Never
the model's deliberation. `REDACTED_PAYLOAD_KEYS` is the mechanism, applied by the event
sink before anything is persisted.

Events are frozen. The log is append-only; a rewritten history is not a record.
"""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum

from pydantic import Field

from app.schemas.common import (
    EventId,
    FrozenModel,
    JsonDict,
    NonEmptyStr,
    RunId,
    new_event_id,
    utcnow,
)


class EventType(StrEnum):
    """The closed event vocabulary. Frozen at Phase 2.

    Closed on purpose: the UI renders per type, scenarios assert on ordered sequences of
    them, and the evaluation harness counts them. A type invented ad hoc at a call site
    would be invisible to all three.
    """

    # Run lifecycle
    RUN_STARTED = "RUN_STARTED"
    RUN_COMPLETED = "RUN_COMPLETED"
    RUN_FAILED = "RUN_FAILED"
    RUN_CANCELLED = "RUN_CANCELLED"

    # Understanding and planning
    INTENT_CREATED = "INTENT_CREATED"
    PLAN_CREATED = "PLAN_CREATED"
    PLAN_REVISED = "PLAN_REVISED"
    TASK_GRAPH_CREATED = "TASK_GRAPH_CREATED"

    # Task lifecycle
    TASK_CREATED = "TASK_CREATED"
    TASK_READY = "TASK_READY"
    TASK_STARTED = "TASK_STARTED"
    TASK_COMPLETED = "TASK_COMPLETED"
    TASK_FAILED = "TASK_FAILED"
    TASK_RETRYING = "TASK_RETRYING"
    TASK_BLOCKED = "TASK_BLOCKED"
    TASK_SKIPPED = "TASK_SKIPPED"

    # Tools
    TOOL_SELECTED = "TOOL_SELECTED"
    TOOL_EXECUTED = "TOOL_EXECUTED"
    TOOL_FAILED = "TOOL_FAILED"
    OBSERVATION_RECORDED = "OBSERVATION_RECORDED"

    # Reasoning
    REASONING_STARTED = "REASONING_STARTED"
    FINDING_CREATED = "FINDING_CREATED"
    REASONING_REVISED = "REASONING_REVISED"
    # A claim that was supported by evidence but did not answer the objective.
    # Distinct from FINDING_REJECTED, which means verification found it unsupported:
    # this one may be perfectly true and still not belong in the answer.
    FINDING_DISCARDED = "FINDING_DISCARDED"

    # Verification
    VERIFICATION_STARTED = "VERIFICATION_STARTED"
    FINDING_VERIFIED = "FINDING_VERIFIED"
    FINDING_REJECTED = "FINDING_REJECTED"
    VERIFICATION_DEGRADED = "VERIFICATION_DEGRADED"
    VERIFICATION_COMPLETED = "VERIFICATION_COMPLETED"

    # The adaptive loop
    EVIDENCE_GAP_DETECTED = "EVIDENCE_GAP_DETECTED"
    EVIDENCE_GAP_RESOLVED = "EVIDENCE_GAP_RESOLVED"
    REPLAN_STARTED = "REPLAN_STARTED"
    REPLAN_COMPLETED = "REPLAN_COMPLETED"

    # Output
    SYNTHESIS_STARTED = "SYNTHESIS_STARTED"
    SYNTHESIS_COMPLETED = "SYNTHESIS_COMPLETED"

    # Instrumentation
    LLM_CALL_COMPLETED = "LLM_CALL_COMPLETED"
    BUDGET_WARNING = "BUDGET_WARNING"


# Payload keys stripped before persistence. This is the enforcement point for invariant #3:
# a component may put raw model output in a payload for local debugging, and it will not
# survive to the database, the SSE stream or a trace file.
REDACTED_PAYLOAD_KEYS: frozenset[str] = frozenset(
    {
        "raw_response",
        "raw_completion",
        "prompt",
        "system_prompt",
        "messages",
        "chain_of_thought",
        "reasoning_trace",
        "thinking",
    }
)


# Events that mark a phase boundary, for the UI's phase tracker.
PHASE_EVENTS: frozenset[EventType] = frozenset(
    {
        EventType.INTENT_CREATED,
        EventType.PLAN_CREATED,
        EventType.TASK_GRAPH_CREATED,
        EventType.REASONING_STARTED,
        EventType.VERIFICATION_STARTED,
        EventType.REPLAN_STARTED,
        EventType.SYNTHESIS_STARTED,
        EventType.RUN_COMPLETED,
    }
)


class ExecutionEvent(FrozenModel):
    """One immutable record in a run's timeline."""

    event_id: EventId = Field(default_factory=new_event_id)
    run_id: RunId
    event_type: EventType
    # Milliseconds since RUN_STARTED. This is what produces the `00:00.420 INTENT_CREATED`
    # timeline in the UI and in demo output — wall-clock timestamps would make every trace
    # look different for no useful reason.
    t_offset_ms: int = Field(ge=0)
    payload: JsonDict = Field(default_factory=dict)

    # Correlation, where applicable.
    task_id: str | None = None
    finding_id: str | None = None
    tool_name: str | None = None
    # Which replan iteration this belongs to. 0 = the original pass.
    revision: int = Field(default=0, ge=0)

    timestamp: datetime = Field(default_factory=utcnow)

    @property
    def offset_display(self) -> str:
        """`00:06.900` — the trace format used in demos and the timeline panel."""
        total_s, ms = divmod(self.t_offset_ms, 1000)
        minutes, seconds = divmod(total_s, 60)
        return f"{minutes:02d}:{seconds:02d}.{ms:03d}"

    def redacted(self) -> ExecutionEvent:
        """A copy with model deliberation removed. Applied before persistence."""
        if not (REDACTED_PAYLOAD_KEYS & self.payload.keys()):
            return self
        clean = {k: v for k, v in self.payload.items() if k not in REDACTED_PAYLOAD_KEYS}
        return self.model_copy(update={"payload": clean})

    def describe(self) -> str:
        """One operator-readable line, ASCII only (see BUG-001)."""
        subject = self.task_id or self.finding_id or self.tool_name or ""
        return f"{self.offset_display} {self.event_type.value} {subject}".rstrip()


class EventFilter(FrozenModel):
    """Query parameters for reading a run's events."""

    run_id: RunId
    types: set[EventType] | None = None
    task_id: str | None = None
    # For SSE reconnection: replay everything after this offset.
    after_offset_ms: int | None = Field(default=None, ge=0)
    limit: int = Field(default=500, ge=1, le=5000)

    def matches(self, event: ExecutionEvent) -> bool:
        if event.run_id != self.run_id:
            return False
        if self.types is not None and event.event_type not in self.types:
            return False
        if self.task_id is not None and event.task_id != self.task_id:
            return False
        if self.after_offset_ms is not None and event.t_offset_ms <= self.after_offset_ms:
            return False
        return True


class ExecutionTrace(FrozenModel):
    """A complete recorded run: the file format written to `.agent/traces/`.

    Never hand-authored. A hand-written trace is evidence of behaviour that never happened.
    """

    run_id: RunId
    objective: NonEmptyStr
    recorded_at: datetime = Field(default_factory=utcnow)
    model: str = ""
    prompt_versions: dict[str, int] = Field(default_factory=dict)
    config_hash: str = ""
    outcome: str = ""
    events: list[ExecutionEvent] = Field(default_factory=list)

    @property
    def duration_ms(self) -> int:
        return self.events[-1].t_offset_ms if self.events else 0

    def of_type(self, event_type: EventType) -> list[ExecutionEvent]:
        return [e for e in self.events if e.event_type is event_type]

    def contains_ordered(self, sequence: list[EventType]) -> bool:
        """Whether these event types appear in this relative order.

        The core scenario assertion (Phase 20): a scenario proves the agent *did the work*
        by requiring that, say, EVIDENCE_GAP_DETECTED precedes REPLAN_STARTED precedes
        TASK_CREATED. Asserting on the final report would not catch an agent that skipped
        the middle and guessed.
        """
        remaining = list(sequence)
        for event in self.events:
            if remaining and event.event_type is remaining[0]:
                remaining.pop(0)
        return not remaining
