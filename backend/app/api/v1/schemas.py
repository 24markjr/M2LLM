"""Request and response bodies for v1.

These are deliberately separate from the internal schemas. `MissionResult` carries a plan, a
task graph and every observation a run made; a mission list needs none of that, and returning
it would make the list response grow with the size of the investigation. Equally, the wire
format is a contract with the frontend - coupling it directly to internal models means an
internal rename becomes a breaking API change.
"""

from __future__ import annotations

from datetime import datetime

from pydantic import Field

from app.orchestration.mission import MissionStatus, Stage
from app.schemas.common import JarvisModel
from app.schemas.finding import Finding
from app.schemas.task import TaskStatus, TaskType


class CreateMissionRequest(JarvisModel):
    objective: str = Field(min_length=8, max_length=2000)
    documents: list[str] = Field(default_factory=list, max_length=64)


class MissionSummary(JarvisModel):
    """One row in the mission list."""

    run_id: str
    objective: str
    status: MissionStatus
    stage: Stage
    documents: list[str] = Field(default_factory=list)
    created_at: datetime
    finished_at: datetime | None = None

    finding_count: int = 0
    verified_count: int = 0
    unresolved_gap_count: int = 0


class MissionDetail(MissionSummary):
    """A mission's current state, without the full event log."""

    goal: str = ""
    required_operations: list[str] = Field(default_factory=list)
    task_count: int = 0
    replan_iterations: int = 0
    termination_reason: str = ""
    error_code: str = ""
    error_message: str = ""
    clarification_question: str = ""
    has_report: bool = False


class TaskNode(JarvisModel):
    task_id: str
    task_type: TaskType
    description: str = ""
    status: TaskStatus
    depends_on: list[str] = Field(default_factory=list)
    tool_id: str = ""
    # True when the replanning loop inserted this task rather than the planner. This is the
    # adaptive behaviour made visible: without it an inserted task is indistinguishable from
    # one that was planned from the start.
    inserted_by_replan: bool = False


class TaskGraphResponse(JarvisModel):
    run_id: str
    nodes: list[TaskNode] = Field(default_factory=list)
    edges: list[tuple[str, str]] = Field(default_factory=list)
    # Tasks that can run at the same time, in waves. Computed server side because it is a
    # property of the graph, not a layout choice the client should have to re-derive.
    waves: list[list[str]] = Field(default_factory=list)


class EventRecord(JarvisModel):
    event_id: str
    event_type: str
    t_offset_ms: int
    task_id: str | None = None
    finding_id: str | None = None
    payload: dict[str, object] = Field(default_factory=dict)


class EventPage(JarvisModel):
    run_id: str
    events: list[EventRecord] = Field(default_factory=list)
    total: int = 0
    offset: int = 0
    limit: int = 0


class FindingsResponse(JarvisModel):
    run_id: str
    findings: list[Finding] = Field(default_factory=list)
    # Findings are returned whole, with evidence and verification attached. Splitting them
    # across endpoints would let a client render a claim before its verification state
    # arrived, and a claim shown without its verification state is a claim overstated.


class GapRecord(JarvisModel):
    gap_id: str
    gap_type: str
    description: str
    resolved: bool
    finding_id: str = ""


class CancelResponse(JarvisModel):
    run_id: str
    cancelling: bool
    status: MissionStatus
