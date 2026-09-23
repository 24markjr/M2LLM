"""Tool contracts: what a capability is, how it is invoked, and what comes back.

Tools are the only way the agent reads or affects anything. Everything here is designed so
that routing can be decided *deterministically wherever possible* — capability class and
schema compatibility are structural facts, not judgement calls, and only genuine ties reach
the model (Phase 10).
"""

from __future__ import annotations

from enum import StrEnum

from pydantic import Field

from app.schemas.common import (
    CostHint,
    FailureClass,
    JarvisModel,
    JsonDict,
    NonEmptyStr,
    ToolCallId,
    UnitFloat,
    new_tool_call_id,
)


class ToolCapability(StrEnum):
    """What a tool can do, as a class rather than an identity.

    The router filters on these before consulting any model. That is what makes tool
    selection measurable and largely model-independent: routing to the wrong tool within
    the right capability class is a different, lesser failure than routing to the wrong
    class entirely, and Phase 20 scores them separately.
    """

    DOCUMENT_SEARCH = "DOCUMENT_SEARCH"
    DOCUMENT_EXTRACT = "DOCUMENT_EXTRACT"
    TABULAR_ANALYSIS = "TABULAR_ANALYSIS"
    COMPUTATION = "COMPUTATION"
    EVIDENCE_RETRIEVAL = "EVIDENCE_RETRIEVAL"
    CONTEXT_RETRIEVAL = "CONTEXT_RETRIEVAL"
    KNOWLEDGE_SEARCH = "KNOWLEDGE_SEARCH"
    VERIFICATION = "VERIFICATION"


class ToolDefinition(JarvisModel):
    """A tool's public description.

    This is what the registry exports into the planner prompt, so the model plans against
    capabilities that actually exist rather than ones it imagines.
    """

    name: NonEmptyStr
    description: NonEmptyStr
    capabilities: set[ToolCapability] = Field(min_length=1)
    # JSON Schema derived from the tool's Pydantic input/output models.
    input_schema: JsonDict
    output_schema: JsonDict
    cost_hint: CostHint = CostHint.LOW
    timeout_s: float = Field(default=30.0, gt=0)
    enabled: bool = True

    def serves(self, capability: ToolCapability) -> bool:
        return capability in self.capabilities


class SelectionMode(StrEnum):
    """How a tool came to be chosen. Recorded for every selection.

    `DETERMINISTIC` selections are the healthy majority: exactly one capable,
    schema-compatible tool existed. A rising share of `LLM_TIEBREAK` means the capability
    model has become too coarse to discriminate, which is a design signal worth seeing.
    """

    DETERMINISTIC = "DETERMINISTIC"
    LLM_TIEBREAK = "LLM_TIEBREAK"
    FALLBACK = "FALLBACK"
    EXPLICIT_HINT = "EXPLICIT_HINT"


class ToolSelection(JarvisModel):
    """The router's decision, with its reasoning made inspectable."""

    tool_name: NonEmptyStr
    capability: ToolCapability
    mode: SelectionMode
    reason: str = ""
    alternatives_considered: list[str] = Field(default_factory=list)
    confidence: UnitFloat = 1.0


class ToolCall(JarvisModel):
    """An invocation of a tool. Validated against the tool's input schema before dispatch."""

    call_id: ToolCallId = Field(default_factory=new_tool_call_id)
    tool_name: NonEmptyStr
    arguments: JsonDict = Field(default_factory=dict)
    timeout_s: float | None = Field(default=None, gt=0)


class ToolError(JarvisModel):
    """A tool failure, classified so the execution engine knows what to do about it.

    `failure_class` decides retry vs. fallback vs. clean degradation. An unclassified error
    would make that decision guesswork.
    """

    failure_class: FailureClass
    message: NonEmptyStr
    # Present when a fallback tool was tried after this failure.
    recovered_by: str | None = None


class ToolResult(JarvisModel):
    """What a tool returned, successfully or not.

    `sources` is the load-bearing field. A tool that produced content without saying where
    it came from yields evidence that cannot be resolved, which in turn caps the confidence
    of anything built on it. Retrieval tools must populate it.
    """

    call_id: ToolCallId
    tool_name: NonEmptyStr
    ok: bool
    output: JsonDict = Field(default_factory=dict)
    error: ToolError | None = None
    execution_time_ms: int = Field(default=0, ge=0)
    # Source locators, in compact `document.pdf:p12` form, for anything retrieved.
    sources: list[str] = Field(default_factory=list)

    @property
    def failed(self) -> bool:
        return not self.ok

    @property
    def is_retryable(self) -> bool:
        from app.schemas.common import is_retryable

        return self.error is not None and is_retryable(self.error.failure_class)
