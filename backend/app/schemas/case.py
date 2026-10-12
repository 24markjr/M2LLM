"""Cases (Phase 44): the unit an investigation is organised, owned and closed by.

A mission answers one question. A case is the matter the questions are about: it holds the
evidence, the investigations run over it, and (from Phase 50) the reviews and the audit trail, under
one number a person can quote - `CASE-2026-00001`. Every count on a case is computed from what it
holds, never stored as a number someone could forget to update.
"""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum

from pydantic import Field

from app.schemas.common import JarvisModel, utcnow

CASE_ID = r"^CASE-\d{4}-\d{5,}$"


class CaseSeverity(StrEnum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"


class CaseStatus(StrEnum):
    OPEN = "OPEN"
    INVESTIGATING = "INVESTIGATING"
    REVIEW = "REVIEW"
    CLOSED = "CLOSED"


class CaseMode(StrEnum):
    GENERAL = "GENERAL"
    # Cyber investigation mode (Phase 52): event logs, indicators, per-host and per-account
    # timelines, and the ATT&CK view (Phase 53).
    CYBER = "CYBER"


class Case(JarvisModel):
    case_id: str = Field(pattern=CASE_ID)
    title: str = Field(min_length=3, max_length=200)
    description: str = Field(default="", max_length=4000)
    severity: CaseSeverity = CaseSeverity.MEDIUM
    status: CaseStatus = CaseStatus.OPEN
    owner: str = Field(default="unassigned", max_length=128)
    mode: CaseMode = CaseMode.GENERAL
    # Opt-in (decision D19): show other cases sharing indicators with this one, as context. Never
    # evidence - nothing recalled can be cited by a finding.
    recall_similar: bool = False
    opened_at: datetime = Field(default_factory=utcnow)
    closed_at: datetime | None = None


class CaseInvestigation(JarvisModel):
    """A mission run in a case, with the outcome it reached (kept when the run ends, so a case still
    knows its investigations after the engine restarts)."""

    case_id: str
    run_id: str
    objective: str
    status: str = "PENDING"
    findings: int = 0
    verified: int = 0
    contradictions: int = 0
    open_gaps: int = 0
    created_at: datetime = Field(default_factory=utcnow)
    finished_at: datetime | None = None


class CaseEvidence(JarvisModel):
    """An evidence item held by a case. The same item can be in several cases."""

    case_id: str
    evidence_id: str
    added_at: datetime = Field(default_factory=utcnow)
    added_by: str = "system"


class CaseCounters(JarvisModel):
    investigations: int = 0
    running: int = 0
    evidence: int = 0
    failed_integrity: int = 0
    findings: int = 0
    verified: int = 0
    contradictions: int = 0
    open_gaps: int = 0
