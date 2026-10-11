"""The Evidence Locker (Phase 43): every input as an evidence object with a provable history.

A document used to be a file in a folder, known by its name. An investigation that will be relied
on needs more: which exact bytes were examined (a SHA-256), where they came from and who brought
them in, and an unbroken record of everything done to them since - read, understood, indexed,
analysed by a mission, cited by a finding. That record is the chain of custody, and it is
append-only: a history that can be edited is not evidence of anything.

The same bytes are one evidence item however often they arrive: identity is the hash, not the
name. A file re-uploaded under the same name with different content is a new item.
"""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Any

from pydantic import Field

from app.schemas.common import JarvisModel, utcnow


class EvidenceClassification(StrEnum):
    """Handling sensitivity, set by a person. Enforced by access control in Phase 55."""

    UNCLASSIFIED = "UNCLASSIFIED"
    INTERNAL = "INTERNAL"
    CONFIDENTIAL = "CONFIDENTIAL"
    RESTRICTED = "RESTRICTED"


class IntegrityStatus(StrEnum):
    # The stored bytes and the working copy hash to the recorded SHA-256.
    VERIFIED = "VERIFIED"
    # They do not. The item is excluded from new missions; findings citing it are flagged.
    FAILED = "FAILED"
    UNCHECKED = "UNCHECKED"


class CustodyAction(StrEnum):
    """What can happen to evidence. A closed vocabulary, like every other in the system."""

    ACQUIRED = "ACQUIRED"
    HASHED = "HASHED"
    STORED = "STORED"
    # Already in the folders before the locker existed: its earlier history is unknown, and says so.
    IMPORTED = "IMPORTED"
    PARSED = "PARSED"
    PARSE_FAILED = "PARSE_FAILED"
    UNDERSTOOD = "UNDERSTOOD"
    INDEXED = "INDEXED"
    ANALYSED = "ANALYSED"
    CITED = "CITED"
    REPORTED = "REPORTED"
    VERIFIED = "VERIFIED"
    INTEGRITY_FAILED = "INTEGRITY_FAILED"
    METADATA_CHANGED = "METADATA_CHANGED"


class EvidenceItem(JarvisModel):
    evidence_id: str = Field(pattern=r"^EV-\d{6,}$")
    sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    # The name it arrived under, which is also how missions refer to it.
    name: str
    kind: str = ""
    parser: str = ""
    bytes: int = Field(default=0, ge=0)
    collected_at: datetime = Field(default_factory=utcnow)
    collected_by: str = "unknown"
    # Where it came from, in words: "uploaded through the console", "repository fixture".
    source: str = ""
    classification: EvidenceClassification = EvidenceClassification.UNCLASSIFIED
    # How much weight the source carries (Phase 45): a tier from `.agent/config/authority.yaml`, set
    # at intake by its rules and overridable by a person (recorded as METADATA_CHANGED). Reported on
    # both sides of a contradiction; it never decides one.
    authority: str = Field(default="UNASSESSED", max_length=32)
    authority_reason: str = Field(default="", max_length=300)
    integrity: IntegrityStatus = IntegrityStatus.UNCHECKED
    integrity_checked_at: datetime | None = None
    # Case membership arrives in Phase 44.
    case_id: str | None = None


class CustodyEvent(JarvisModel):
    """One link in the chain. Never updated, never deleted."""

    event_id: int = 0
    evidence_id: str
    action: CustodyAction
    actor: str = "system"
    at: datetime = Field(default_factory=utcnow)
    details: dict[str, Any] = Field(default_factory=dict)


class EvidenceCitation(JarvisModel):
    """A finding that cited this evidence, from its CITED custody event."""

    run_id: str
    finding_id: str
    locator: str
    claim: str = ""
    at: datetime


class IntegrityCheck(JarvisModel):
    evidence_id: str
    integrity: IntegrityStatus
    expected: str
    # The hash of the stored original, and of the working copy missions read (when there is one).
    stored: str | None = None
    working: str | None = None
    reason: str = ""
