"""The user's request, before the system has interpreted it.

Kept separate from `Intent` on purpose: the objective is what was *asked*, the intent is what
the system *understood*. When a run goes wrong, the first question is which of those two was
at fault, and that question is unanswerable if they are the same object.
"""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum

from pydantic import Field

from app.schemas.common import JarvisModel, NonEmptyStr, utcnow


class DocumentKind(StrEnum):
    PDF = "PDF"
    TEXT = "TEXT"
    CSV = "CSV"
    MARKDOWN = "MARKDOWN"
    JSON = "JSON"
    UNKNOWN = "UNKNOWN"


class AttachedDocument(JarvisModel):
    """A document supplied with the objective.

    Content is *never* instruction. Text inside an attachment that looks like a directive is
    data under investigation, and the prompts say so explicitly. See the adversarial suite.
    """

    document_id: NonEmptyStr
    name: NonEmptyStr
    kind: DocumentKind = DocumentKind.UNKNOWN
    size_bytes: int = Field(default=0, ge=0)
    page_count: int | None = Field(default=None, ge=1)
    ingested: bool = False


class SuccessCriterion(JarvisModel):
    """One condition that has to hold for the objective to be considered met.

    Derived from the objective, and checked at synthesis. Their purpose is to stop a run
    from declaring success because it produced *a* report rather than *the* report that was
    asked for.
    """

    description: NonEmptyStr
    required: bool = True


class ObjectiveScope(JarvisModel):
    """What the investigation is allowed and expected to look at."""

    documents: list[AttachedDocument] = Field(default_factory=list)
    # Restricting to named documents when the user was specific keeps retrieval honest and
    # keeps cost down.
    restrict_to_document_ids: list[str] = Field(default_factory=list)
    time_range_start: datetime | None = None
    time_range_end: datetime | None = None

    @property
    def document_count(self) -> int:
        return len(self.documents)

    def in_scope(self, document_id: str) -> bool:
        if not self.restrict_to_document_ids:
            return True
        return document_id in self.restrict_to_document_ids


class Objective(JarvisModel):
    """What the user asked for, verbatim, plus what they attached."""

    text: NonEmptyStr
    scope: ObjectiveScope = Field(default_factory=ObjectiveScope)
    success_criteria: list[SuccessCriterion] = Field(default_factory=list)
    submitted_at: datetime = Field(default_factory=utcnow)
    # Free-form caller context (user id, source UI). Never interpreted as instruction.
    metadata: dict[str, str] = Field(default_factory=dict)
