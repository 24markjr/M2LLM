"""What a conversation keeps (v4 Phase 3)."""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Any

from pydantic import Field

from app.schemas.common import JarvisModel, utcnow


class StopReason(StrEnum):
    # The model answered within its tool budget.
    ANSWERED = "ANSWERED"
    # The model needs something only the person can give, and asked.
    ASKED_USER = "ASKED_USER"
    # The tool budget ran out; the answer was written from what the tools had returned.
    STEP_LIMIT = "STEP_LIMIT"
    # The model could not produce a usable step; the turn says so rather than guessing.
    FAILED = "FAILED"
    # Only re-checks were asked for: no model loop ran.
    RECHECKED = "RECHECKED"


class ToolStep(JarvisModel):
    tool: str
    arguments: dict[str, Any] = Field(default_factory=dict)
    # What the tool returned, as the model saw it (bounded): the record of what the answer rests on.
    result: str = ""


class AnsweredClaim(JarvisModel):
    text: str
    citations: list[str] = Field(default_factory=list)
    # The verifier's verdict, or UNVERIFIED when nothing it cites resolves to a line of the case.
    status: str = "UNVERIFIED"
    issues: list[str] = Field(default_factory=list)


class Recheck(JarvisModel):
    """A finding checked again against the case's documents as they are now."""

    run_id: str
    finding_id: str
    claim: str
    before: str
    after: str
    changed: bool
    reason: str = ""


class Turn(JarvisModel):
    turn_id: str
    role: str  # "user" or "assistant"
    text: str
    actor: str = ""
    claims: list[AnsweredClaim] = Field(default_factory=list)
    steps: list[ToolStep] = Field(default_factory=list)
    stop_reason: StopReason | None = None
    # Findings the message named (F-002, or run_x/F-002), and what re-checking them found.
    findings_referred: list[str] = Field(default_factory=list)
    rechecks: list[Recheck] = Field(default_factory=list)
    # A question the assistant put to the person (`ask_user`), answered by their next message.
    question: str = ""
    pinned: bool = False
    created_at: datetime = Field(default_factory=utcnow)


class Thread(JarvisModel):
    case_id: str
    turns: list[Turn] = Field(default_factory=list)
