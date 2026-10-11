"""Human review of findings, and the audit log of every action (Phase 50).

A finding the rules say needs a person's judgement - a contradiction, a claim only described, one a
challenge contested, any finding in a HIGH or CRITICAL case - waits as PENDING until a reviewer
approves, rejects or modifies it. Each decision is a new record with who, when and why; the latest
is the finding's state, and none is ever edited (append-only in Postgres, like custody).

The audit log records every write the API accepts or refuses - who, what, when, the outcome - and
the system's own actions (a mission started, a review decided, a fact remembered).
"""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Any

from pydantic import Field, model_validator

from app.schemas.common import JarvisModel, utcnow


class ReviewState(StrEnum):
    PENDING = "PENDING"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"
    # Approved with its claim reworded by the reviewer; the original stays on record.
    MODIFIED = "MODIFIED"


class ReviewDecision(JarvisModel):
    decision_id: int = 0
    run_id: str
    finding_id: str
    state: ReviewState
    reviewer: str = Field(min_length=1, max_length=128)
    reason: str = Field(default="", max_length=2000)
    modified_claim: str = Field(default="", max_length=2000)
    at: datetime = Field(default_factory=utcnow)

    @model_validator(mode="after")
    def _decisions_say_why(self) -> ReviewDecision:
        if self.state in (ReviewState.REJECTED, ReviewState.MODIFIED) and not self.reason.strip():
            raise ValueError(f"a {self.state.value} decision must give its reason")
        if self.state is ReviewState.MODIFIED and not self.modified_claim.strip():
            raise ValueError("a MODIFIED decision must give the reworded claim")
        return self


class FindingReview(JarvisModel):
    """A finding's review: whether it needs one and why, its state, and every decision."""

    run_id: str
    finding_id: str
    claim: str
    statement_type: str = ""
    required: bool = False
    required_because: list[str] = Field(default_factory=list)
    state: ReviewState = ReviewState.PENDING
    history: list[ReviewDecision] = Field(default_factory=list)

    @property
    def settled(self) -> bool:
        """Approved, modified, or not requiring review at all."""
        return not self.required or self.state in (ReviewState.APPROVED, ReviewState.MODIFIED)


class AuditEntry(JarvisModel):
    entry_id: int = 0
    at: datetime = Field(default_factory=utcnow)
    actor: str = "system"
    # "POST /api/v1/missions" for a request; a verb for the system's own ("mission.started").
    action: str
    target: str = ""
    status_code: int | None = None
    details: dict[str, Any] = Field(default_factory=dict)
