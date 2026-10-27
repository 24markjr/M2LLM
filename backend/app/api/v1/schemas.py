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
from app.schemas.objective import InvestigationMode
from app.schemas.task import TaskStatus, TaskType
from app.schemas.trust import InjectionScan


class CreateMissionRequest(JarvisModel):
    objective: str = Field(min_length=8, max_length=2000)
    documents: list[str] = Field(default_factory=list, max_length=64)
    # The workspace whose stored retrieval the mission searches (Phase 40). The mission's documents
    # are ingested into it first. Absent: no stored retrieval, recall is lexical as before.
    workspace_id: str | None = Field(default=None, pattern=r"^[A-Za-z0-9_-]{1,64}$")
    # The case the investigation belongs to (Phase 44). Its documents are filed in the case too.
    case_id: str | None = Field(default=None, pattern=r"^CASE-\d{4}-\d{5,}$")
    # How to run it (Phase U4): each mode makes certain operations required in the plan.
    mode: InvestigationMode = InvestigationMode.INVESTIGATE


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
    # The case this investigation belongs to (Phase 44); empty for one run outside any case.
    case_id: str = ""
    # How it was asked to run (Phase U4).
    mode: InvestigationMode = InvestigationMode.INVESTIGATE


class MissionDetail(MissionSummary):
    """A mission's current state, without the full event log."""

    goal: str = ""
    required_operations: list[str] = Field(default_factory=list)
    # Where it waits (v4 Phase 8): 1 starts next; 0 when it is not waiting.
    queue_position: int = 0
    task_count: int = 0
    replan_iterations: int = 0
    termination_reason: str = ""
    error_code: str = ""
    error_message: str = ""
    clarification_question: str = ""
    has_report: bool = False
    # Documents flagged by the prompt-injection scan (Phase 27). Each was still read, as data.
    security_flags: list[InjectionScan] = Field(default_factory=list)
    # The mission's knowledge base, when one was built (Phase 31): where it is held and how
    # big it is. Empty `knowledge_store` means none was built. Details: /knowledge routes.
    knowledge_store: str = ""
    knowledge_entities: int = 0
    knowledge_claims: int = 0
    knowledge_conflicts: int = 0
    # The Evidence Locker (Phase 43): document name to the evidence item the mission read, and the
    # documents left out because they failed their integrity check, with the reason.
    evidence: dict[str, str] = Field(default_factory=dict)
    excluded_documents: dict[str, str] = Field(default_factory=dict)
    # Each document's source authority tier (Phase 45), shown on both sides of a contradiction.
    authority: dict[str, str] = Field(default_factory=dict)


class TaskNode(JarvisModel):
    task_id: str
    task_type: TaskType
    description: str = ""
    status: TaskStatus
    depends_on: list[str] = Field(default_factory=list)
    tool_id: str = ""
    # The step in plain language, in the tense its status calls for (Phase 44).
    label: str = ""
    # True when the replanning loop inserted this task rather than the planner. This is the
    # adaptive behaviour made visible: without it an inserted task is indistinguishable from
    # one that was planned from the start.
    inserted_by_replan: bool = False
    # Why it is in the plan and its workstream (Phase 49).
    rationale: str = ""
    workstream: str = ""


class PlanStep(JarvisModel):
    """One task in the plan tree (Phase 49): why, what it took in, what it did, what came out."""

    task_id: str
    label: str
    task_type: str
    why: str
    inputs: list[str] = Field(default_factory=list)
    action: str = ""
    output: str = ""
    depends_on: list[str] = Field(default_factory=list)
    status: TaskStatus
    inserted_by_revision: int = 0


class PlanWorkstream(JarvisModel):
    name: str
    steps: list[PlanStep] = Field(default_factory=list)


class PlanChange(JarvisModel):
    """One "JARVIS changed its plan": what triggered it, why, and the plan before and after."""

    revision: int
    trigger: str
    reason: str
    triggered_by: str = ""
    added: list[PlanStep] = Field(default_factory=list)
    skipped: list[str] = Field(default_factory=list)
    tasks_before: int = 0
    tasks_after: int = 0


class PlanTree(JarvisModel):
    """Objective -> workstreams -> steps, and every change the run made to its plan (Phase 49)."""

    run_id: str
    objective: str
    workstreams: list[PlanWorkstream] = Field(default_factory=list)
    changes: list[PlanChange] = Field(default_factory=list)
    # How the plan came to be valid: the repairs applied, in words.
    repairs: list[str] = Field(default_factory=list)


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
    # Why each finding has its confidence, and why not higher (Phase 46): finding id -> sentences
    # whose numbers add up, from the stored factors.
    why: dict[str, list[str]] = Field(default_factory=dict)
    # Findings are returned whole, with evidence and verification attached. Splitting them
    # across endpoints would let a client render a claim before its verification state
    # arrived, and a claim shown without its verification state is a claim overstated.


class ChainEvidence(JarvisModel):
    """One citation in a finding's evidence chain (Phase 46)."""

    locator: str
    document: str
    resolved: bool
    note: str = ""
    # The Evidence Locker item the mission read under this name, and its source authority.
    evidence_id: str = ""
    authority: str = ""
    # The text at the cited line (or the matched lines on a cited page), as verification read it.
    text: str = ""
    # What the knowledge pass extracted from this line: "Entity.attribute = value".
    extractions: list[str] = Field(default_factory=list)


class ChainStep(JarvisModel):
    """One link from claim to conclusion, in order."""

    kind: str  # CLAIM | EVIDENCE | EXTRACTION | REASONING | VERIFICATION | CONCLUSION
    title: str
    detail: str = ""


class FindingChain(JarvisModel):
    """How a finding came to be what it is: claim -> evidence -> extraction -> reasoning ->
    verification -> conclusion, each step with what it rests on (Phase 46)."""

    run_id: str
    finding: Finding
    why: list[str] = Field(default_factory=list)
    evidence: list[ChainEvidence] = Field(default_factory=list)
    steps: list[ChainStep] = Field(default_factory=list)


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
