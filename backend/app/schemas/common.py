"""Shared primitives for the domain schemas.

Everything crossing a component boundary is built from these (invariant #2). Keeping the
base here means identifier rules, timestamps and serialization behaviour are defined once
rather than re-decided per module.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from enum import StrEnum
from typing import Annotated, Any

from pydantic import BaseModel, ConfigDict, Field, StringConstraints

# --- Identifiers ---------------------------------------------------------------

# Ids are human-readable on purpose. A trace, a log line and a report all show them, and
# "task_004 depends on task_002" is legible in a way that a pair of UUIDs is not.
RunId = Annotated[str, StringConstraints(pattern=r"^run_[0-9a-f]{12}$")]
TaskId = Annotated[str, StringConstraints(pattern=r"^task_\d{3,}$")]
FindingId = Annotated[str, StringConstraints(pattern=r"^F-\d{3,}$")]
EvidenceId = Annotated[str, StringConstraints(pattern=r"^E-\d{3,}$")]
GapId = Annotated[str, StringConstraints(pattern=r"^G-\d{3,}$")]
EventId = Annotated[str, StringConstraints(pattern=r"^evt_[0-9a-f]{12}$")]
ToolCallId = Annotated[str, StringConstraints(pattern=r"^call_[0-9a-f]{12}$")]

# Confidence and other normalized scores. The bounds are enforced by the type, so no
# component has to remember to clamp.
UnitFloat = Annotated[float, Field(ge=0.0, le=1.0)]

NonEmptyStr = Annotated[str, StringConstraints(min_length=1, strip_whitespace=True)]


def _short_hex() -> str:
    return uuid.uuid4().hex[:12]


def new_run_id() -> str:
    return f"run_{_short_hex()}"


def new_event_id() -> str:
    return f"evt_{_short_hex()}"


def new_tool_call_id() -> str:
    return f"call_{_short_hex()}"


def task_id(n: int) -> str:
    """Task ids are sequential within a run, so a plan reads as an ordered list."""
    return f"task_{n:03d}"


def finding_id(n: int) -> str:
    return f"F-{n:03d}"


def evidence_id(n: int) -> str:
    return f"E-{n:03d}"


def gap_id(n: int) -> str:
    return f"G-{n:03d}"


def utcnow() -> datetime:
    return datetime.now(UTC)


# --- Base model ----------------------------------------------------------------


class JarvisModel(BaseModel):
    """Base for every domain model.

    `extra="forbid"` is deliberate and load-bearing: these models parse LLM output. A model
    that invents a field should fail validation loudly and trigger the repair loop, not have
    the field silently dropped and produce a plausible-looking object that is missing
    information nobody noticed was there.
    """

    model_config = ConfigDict(
        extra="forbid",
        validate_assignment=True,
        use_enum_values=False,
        ser_json_timedelta="float",
        str_strip_whitespace=True,
    )


class FrozenModel(JarvisModel):
    """For values that must not change after creation — events, recorded results."""

    model_config = ConfigDict(
        extra="forbid",
        frozen=True,
        str_strip_whitespace=True,
    )


# --- Shared vocabulary ---------------------------------------------------------


class Severity(StrEnum):
    INFO = "INFO"
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"


class CostHint(StrEnum):
    """Coarse cost class for a tool, used by the Phase 17 planning policy.

    Deliberately three buckets. Finer granularity here would be false precision — we do not
    know a tool's cost well enough to justify more.
    """

    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"


class FailureClass(StrEnum):
    """Why something failed, and therefore whether retrying it could possibly help.

    The split drives `retry.py` (Phase 11): a timeout may succeed on the second attempt;
    a schema violation will fail identically every time, and retrying it only burns budget.
    """

    # Transient — retry may succeed
    TIMEOUT = "TIMEOUT"
    CONNECTION_ERROR = "CONNECTION_ERROR"
    PROVIDER_UNAVAILABLE = "PROVIDER_UNAVAILABLE"
    RATE_LIMITED = "RATE_LIMITED"

    # Permanent — retry is pointless
    SCHEMA_VIOLATION = "SCHEMA_VIOLATION"
    MISSING_INPUT = "MISSING_INPUT"
    UNSAFE_EXPRESSION = "UNSAFE_EXPRESSION"
    NO_CAPABLE_TOOL = "NO_CAPABLE_TOOL"
    NOT_FOUND = "NOT_FOUND"
    INTERNAL_ERROR = "INTERNAL_ERROR"

    # Control flow
    CANCELLED = "CANCELLED"
    BUDGET_EXHAUSTED = "BUDGET_EXHAUSTED"


TRANSIENT_FAILURES: frozenset[FailureClass] = frozenset(
    {
        FailureClass.TIMEOUT,
        FailureClass.CONNECTION_ERROR,
        FailureClass.PROVIDER_UNAVAILABLE,
        FailureClass.RATE_LIMITED,
    }
)


def is_retryable(failure: FailureClass) -> bool:
    return failure in TRANSIENT_FAILURES


class SourceLocator(JarvisModel):
    """Exactly where a piece of content came from.

    This is what makes evidence checkable rather than decorative. "doc_A says the project
    slipped" is an assertion; "project_report.pdf page 12, chars 400-520" is something a
    reader can go and verify, and something the evidence binder can resolve against the
    chunks actually retrieved.
    """

    document_id: NonEmptyStr
    document_name: str = ""
    page: int | None = Field(default=None, ge=1)
    row: int | None = Field(default=None, ge=0)
    char_start: int | None = Field(default=None, ge=0)
    char_end: int | None = Field(default=None, ge=0)

    def as_ref(self) -> str:
        """Compact form used in reports and traces, e.g. `project_report.pdf:p12`."""
        name = self.document_name or self.document_id
        if self.page is not None:
            return f"{name}:p{self.page}"
        if self.row is not None:
            return f"{name}:r{self.row}"
        if self.char_start is not None:
            return f"{name}:c{self.char_start}"
        return name


class Money(JarvisModel):
    """Amounts stay exact.

    Financial comparison is a core part of the investigation domain, and a contradiction
    detected because of float drift would be a fabricated finding.
    """

    amount: str = Field(pattern=r"^-?\d+(\.\d+)?$")
    currency: str = Field(default="USD", min_length=3, max_length=3)


JsonDict = dict[str, Any]
