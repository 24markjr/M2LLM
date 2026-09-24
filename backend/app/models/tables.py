"""SQLAlchemy models — the persistent shape of a run.

Until now a run lived in memory and vanished when the command ended. That was survivable
while the agent was being built, but it makes three later things impossible: the API cannot
serve a run it no longer has, the evaluation harness cannot recompute metrics over past
runs, and nobody can ask "what did it conclude last Tuesday, and on what evidence?"

Two design rules carry through the schema:

**Referential integrity is the point, not decoration.** A finding without its evidence is
exactly the failure this project exists to prevent, so evidence hangs off findings with a
cascade and cannot be orphaned. Deleting a run removes everything it produced, atomically.

**The event log is append-only.** No updates, no deletes. A timeline that can be rewritten
is not a record of what happened.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pgvector.sqlalchemy import Vector
from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship

from app.core.config import get_settings
from app.schemas.common import utcnow

# JSONB on PostgreSQL, JSON elsewhere, so the models stay usable against SQLite in a
# unit test without a second definition.
JsonType = JSON().with_variant(JSONB(), "postgresql")


class Base(DeclarativeBase):
    pass


class AgentRun(Base):
    """One investigation, from objective to outcome."""

    __tablename__ = "agent_runs"

    id: Mapped[str] = mapped_column(String(32), primary_key=True)
    objective: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    current_phase: Mapped[str] = mapped_column(String(32), default="UNDERSTANDING")

    model: Mapped[str] = mapped_column(String(128), default="")
    intent: Mapped[dict[str, Any] | None] = mapped_column(JsonType, nullable=True)
    final_result: Mapped[dict[str, Any] | None] = mapped_column(JsonType, nullable=True)

    termination_reason: Mapped[str | None] = mapped_column(String(32), nullable=True)
    replan_iterations: Mapped[int] = mapped_column(Integer, default=0)
    tool_calls_used: Mapped[int] = mapped_column(Integer, default=0)
    error_code: Mapped[str] = mapped_column(String(64), default="")

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    # Cascades throughout: a run can be purged atomically, and nothing it produced can
    # outlive it as an orphan.
    tasks: Mapped[list[Task]] = relationship(
        back_populates="run", cascade="all, delete-orphan", passive_deletes=True
    )
    findings: Mapped[list[Finding]] = relationship(
        back_populates="run", cascade="all, delete-orphan", passive_deletes=True
    )
    events: Mapped[list[ExecutionEvent]] = relationship(
        back_populates="run", cascade="all, delete-orphan", passive_deletes=True
    )
    tool_executions: Mapped[list[ToolExecution]] = relationship(
        back_populates="run", cascade="all, delete-orphan", passive_deletes=True
    )


class Task(Base):
    __tablename__ = "tasks"
    __table_args__ = (UniqueConstraint("run_id", "task_id", name="uq_task_per_run"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    run_id: Mapped[str] = mapped_column(
        String(32), ForeignKey("agent_runs.id", ondelete="CASCADE"), index=True
    )
    task_id: Mapped[str] = mapped_column(String(32), nullable=False)
    task_type: Mapped[str] = mapped_column(String(64), nullable=False)
    description: Mapped[str] = mapped_column(Text, default="")
    status: Mapped[str] = mapped_column(String(32), nullable=False, index=True)

    inputs: Mapped[dict[str, Any]] = mapped_column(JsonType, default=dict)
    output: Mapped[dict[str, Any] | None] = mapped_column(JsonType, nullable=True)
    selected_tool: Mapped[str] = mapped_column(String(64), default="")
    selection_mode: Mapped[str] = mapped_column(String(32), default="")

    attempts: Mapped[int] = mapped_column(Integer, default=0)
    failure_class: Mapped[str | None] = mapped_column(String(32), nullable=True)
    error_message: Mapped[str] = mapped_column(Text, default="")

    # Provenance for replanning-inserted tasks, so a graph mutation can be explained
    # long after the run finished.
    created_by_revision: Mapped[int] = mapped_column(Integer, default=0)
    created_for_gap_id: Mapped[str | None] = mapped_column(String(32), nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    run: Mapped[AgentRun] = relationship(back_populates="tasks")
    dependencies: Mapped[list[TaskDependency]] = relationship(
        back_populates="task",
        cascade="all, delete-orphan",
        passive_deletes=True,
        foreign_keys="TaskDependency.task_pk",
    )


class TaskDependency(Base):
    """An edge in the task graph, stored as a row so the DAG survives the process."""

    __tablename__ = "task_dependencies"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    task_pk: Mapped[int] = mapped_column(
        Integer, ForeignKey("tasks.id", ondelete="CASCADE"), index=True
    )
    depends_on_task_id: Mapped[str] = mapped_column(String(32), nullable=False)

    task: Mapped[Task] = relationship(back_populates="dependencies", foreign_keys=[task_pk])


class ToolExecution(Base):
    __tablename__ = "tool_executions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    run_id: Mapped[str] = mapped_column(
        String(32), ForeignKey("agent_runs.id", ondelete="CASCADE"), index=True
    )
    task_id: Mapped[str] = mapped_column(String(32), index=True)
    call_id: Mapped[str] = mapped_column(String(32), nullable=False)
    tool_name: Mapped[str] = mapped_column(String(64), nullable=False, index=True)

    arguments: Mapped[dict[str, Any]] = mapped_column(JsonType, default=dict)
    output: Mapped[dict[str, Any]] = mapped_column(JsonType, default=dict)
    ok: Mapped[bool] = mapped_column(Boolean, default=True)
    failure_class: Mapped[str | None] = mapped_column(String(32), nullable=True)
    sources: Mapped[list[str]] = mapped_column(JsonType, default=list)
    execution_time_ms: Mapped[int] = mapped_column(Integer, default=0)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    run: Mapped[AgentRun] = relationship(back_populates="tool_executions")


class Finding(Base):
    __tablename__ = "findings"
    __table_args__ = (UniqueConstraint("run_id", "finding_id", name="uq_finding_per_run"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    run_id: Mapped[str] = mapped_column(
        String(32), ForeignKey("agent_runs.id", ondelete="CASCADE"), index=True
    )
    finding_id: Mapped[str] = mapped_column(String(32), nullable=False)
    claim: Mapped[str] = mapped_column(Text, nullable=False)
    classification: Mapped[str] = mapped_column(String(32), nullable=False, index=True)

    # NUMERIC, not float: a confidence shown in a report must not drift between what was
    # computed and what is displayed.
    confidence: Mapped[float] = mapped_column(Numeric(4, 3), default=0)
    resolution_rate: Mapped[float] = mapped_column(Numeric(4, 3), default=0)
    evidence_strength: Mapped[float] = mapped_column(Numeric(4, 3), default=0)
    source_agreement: Mapped[float] = mapped_column(Numeric(4, 3), default=0)

    revision: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    run: Mapped[AgentRun] = relationship(back_populates="findings")
    evidence: Mapped[list[Evidence]] = relationship(
        back_populates="finding", cascade="all, delete-orphan", passive_deletes=True
    )
    verifications: Mapped[list[Verification]] = relationship(
        back_populates="finding", cascade="all, delete-orphan", passive_deletes=True
    )
    gaps: Mapped[list[EvidenceGap]] = relationship(
        back_populates="finding", cascade="all, delete-orphan", passive_deletes=True
    )


class Evidence(Base):
    """A citation, resolved or not.

    Unresolved references are stored too. Keeping only what resolved would make every
    stored finding look better supported than it was.
    """

    __tablename__ = "evidence"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    finding_pk: Mapped[int] = mapped_column(
        Integer, ForeignKey("findings.id", ondelete="CASCADE"), index=True
    )
    document_id: Mapped[str] = mapped_column(String(255), nullable=False)
    locator: Mapped[str] = mapped_column(String(255), nullable=False)
    page: Mapped[int | None] = mapped_column(Integer, nullable=True)
    row: Mapped[int | None] = mapped_column(Integer, nullable=True)

    content: Mapped[str] = mapped_column(Text, default="")
    resolution: Mapped[str] = mapped_column(String(32), default="UNRESOLVED", index=True)
    resolution_note: Mapped[str] = mapped_column(Text, default="")
    strength: Mapped[str] = mapped_column(String(32), default="DIRECT")
    relevance_score: Mapped[float] = mapped_column(Float, default=1.0)
    retrieved_by_task_id: Mapped[str | None] = mapped_column(String(32), nullable=True)

    finding: Mapped[Finding] = relationship(back_populates="evidence")


class Verification(Base):
    __tablename__ = "verifications"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    finding_pk: Mapped[int] = mapped_column(
        Integer, ForeignKey("findings.id", ondelete="CASCADE"), index=True
    )
    status: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    confidence: Mapped[float] = mapped_column(Numeric(4, 3), default=0)
    verifier: Mapped[str] = mapped_column(String(64), default="baseline")
    # A finding verified by a fallback is not the same as one verified by the service,
    # and a stored result has to preserve that difference.
    degraded: Mapped[bool] = mapped_column(Boolean, default=False)
    degraded_reason: Mapped[str] = mapped_column(Text, default="")
    issues: Mapped[list[dict[str, Any]]] = mapped_column(JsonType, default=list)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    finding: Mapped[Finding] = relationship(back_populates="verifications")


class EvidenceGap(Base):
    __tablename__ = "evidence_gaps"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    finding_pk: Mapped[int] = mapped_column(
        Integer, ForeignKey("findings.id", ondelete="CASCADE"), index=True
    )
    gap_id: Mapped[str] = mapped_column(String(32), nullable=False)
    gap_type: Mapped[str] = mapped_column(String(48), nullable=False, index=True)
    missing: Mapped[str] = mapped_column(Text, nullable=False)
    severity: Mapped[float] = mapped_column(Numeric(4, 3), default=0.5)
    suggested_query: Mapped[str] = mapped_column(Text, default="")
    resolved: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    resolved_by_task_id: Mapped[str | None] = mapped_column(String(32), nullable=True)

    finding: Mapped[Finding] = relationship(back_populates="gaps")


class ExecutionEvent(Base):
    """One entry in the run timeline. Append-only: inserted, never updated or deleted."""

    __tablename__ = "execution_events"
    __table_args__ = (Index("ix_events_run_offset", "run_id", "t_offset_ms"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    event_id: Mapped[str] = mapped_column(String(32), nullable=False)
    run_id: Mapped[str] = mapped_column(
        String(32), ForeignKey("agent_runs.id", ondelete="CASCADE"), index=True
    )
    event_type: Mapped[str] = mapped_column(String(48), nullable=False, index=True)
    t_offset_ms: Mapped[int] = mapped_column(Integer, nullable=False)
    payload: Mapped[dict[str, Any]] = mapped_column(JsonType, default=dict)

    task_id: Mapped[str | None] = mapped_column(String(32), nullable=True)
    finding_id: Mapped[str | None] = mapped_column(String(32), nullable=True)
    tool_name: Mapped[str | None] = mapped_column(String(64), nullable=True)
    revision: Mapped[int] = mapped_column(Integer, default=0)

    timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    run: Mapped[AgentRun] = relationship(back_populates="events")


class Document(Base):
    __tablename__ = "documents"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    document_id: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    kind: Mapped[str] = mapped_column(String(32), default="text")
    page_count: Mapped[int] = mapped_column(Integer, default=0)
    line_count: Mapped[int] = mapped_column(Integer, default=0)
    size_bytes: Mapped[int] = mapped_column(Integer, default=0)
    # A document read only in part must stay distinguishable from one read whole.
    truncated: Mapped[bool] = mapped_column(Boolean, default=False)
    omitted_note: Mapped[str] = mapped_column(Text, default="")

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    chunks: Mapped[list[DocumentChunk]] = relationship(
        back_populates="document", cascade="all, delete-orphan", passive_deletes=True
    )


class DocumentChunk(Base):
    """A retrievable passage with its embedding.

    pgvector lives in the same database as the findings (ADR-005), so the chunk an
    evidence item points at is a join away rather than a cross-system reference nothing
    enforces.
    """

    __tablename__ = "document_chunks"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    document_pk: Mapped[int] = mapped_column(
        Integer, ForeignKey("documents.id", ondelete="CASCADE"), index=True
    )
    chunk_id: Mapped[str] = mapped_column(String(255), nullable=False)
    locator: Mapped[str] = mapped_column(String(255), nullable=False)
    page: Mapped[int | None] = mapped_column(Integer, nullable=True)
    row: Mapped[int | None] = mapped_column(Integer, nullable=True)
    text: Mapped[str] = mapped_column(Text, nullable=False)
    embedding: Mapped[list[float] | None] = mapped_column(
        Vector(get_settings().embedding_dim), nullable=True
    )

    document: Mapped[Document] = relationship(back_populates="chunks")
