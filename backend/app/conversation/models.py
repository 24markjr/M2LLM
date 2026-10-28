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


class TurnTranslation(JarvisModel):
    """An answer in the person's language (v4 Phase 7): a labelled machine translation of the
    verified English, never a second answer."""

    language: str
    language_name: str = ""
    # The browser voice to read it aloud with, e.g. `hi-IN`.
    speech: str = ""
    text: str
    engine: str
    engine_version: str = ""
    fallback: bool = False
    label: str = ""


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
    # Phase 4: replaced by a regenerated answer or an edited message - kept, never deleted, and left
    # out of what the model reads. `replaces` names the turn a new one stands in for.
    superseded: bool = False
    replaces: str = ""
    # v4 Phase 7: the language the person asked in. For their message, `text` is the English the
    # investigation reads and `original_text` what they typed (and `transliterated`, if they typed
    # in Roman letters); for an answer, `text` is the verified English and `translation` its
    # labelled rendering in their language.
    language: str = "en"
    original_text: str = ""
    transliterated: str = ""
    transliteration_engine: str = ""
    translation_engine: str = ""
    language_note: str = ""
    translation: TurnTranslation | None = None
    created_at: datetime = Field(default_factory=utcnow)


class Thread(JarvisModel):
    case_id: str
    turns: list[Turn] = Field(default_factory=list)
