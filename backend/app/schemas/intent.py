"""The system's structured interpretation of an objective.

Produced by the intent engine (Phase 6). The key design property: `required_operations` is
drawn from a **closed vocabulary**. A model that invents an operation does not get it
silently accepted — the operation is either mapped to a known one or flagged
`UNSUPPORTED_OPERATION`, because a plan built on an operation no tool can perform is a plan
that fails late and confusingly instead of early and clearly.
"""

from __future__ import annotations

from enum import StrEnum

from pydantic import Field, field_validator, model_validator

from app.schemas.common import JarvisModel, NonEmptyStr, UnitFloat


class Operation(StrEnum):
    """The closed vocabulary of operations the agent knows how to perform.

    Extending this is a deliberate act: a new operation needs a task type that can execute
    it and at least one tool that can serve it, or planning will produce work that routing
    cannot fulfil.
    """

    # Acquisition
    PROCESS_DOCUMENTS = "process_documents"
    EXTRACT_TIMELINE = "extract_timeline"
    EXTRACT_BUDGET = "extract_budget"
    EXTRACT_MILESTONES = "extract_milestones"
    EXTRACT_ENTITIES = "extract_entities"
    EXTRACT_CLAIMS = "extract_claims"

    # Normalization
    NORMALIZE_DATES = "normalize_dates"
    NORMALIZE_VALUES = "normalize_values"

    # Analysis
    COMPARE_SOURCES = "compare_sources"
    DETECT_INCONSISTENCIES = "detect_inconsistencies"
    DETECT_CONTRADICTIONS = "detect_contradictions"
    CALCULATE_DIFFERENCE = "calculate_difference"
    ASSESS_IMPACT = "assess_impact"
    SUMMARIZE = "summarize"

    # Evidence
    RETRIEVE_EVIDENCE = "retrieve_evidence"
    VERIFY_FINDINGS = "verify_findings"

    # Output
    GENERATE_REPORT = "generate_report"


class OutputFormat(StrEnum):
    INVESTIGATION_REPORT = "investigation_report"
    COMPARISON_TABLE = "comparison_table"
    SUMMARY = "summary"
    FINDING_LIST = "finding_list"


class RequiredOperation(JarvisModel):
    """One operation the intent requires, with why the system believes it is needed.

    The rationale is not decoration: Phase 20 scores intent accuracy against an expected
    operation set, and when a run picks up a spurious operation the rationale is what makes
    the cause diagnosable.
    """

    operation: Operation
    rationale: str = ""
    # Operations the planner may skip if earlier results make them unnecessary.
    optional: bool = False


class UnsupportedOperation(JarvisModel):
    """Something the objective seems to need that the system cannot do.

    Surfaced rather than dropped. An agent that quietly ignores part of a request and
    reports success has lied, and this field is what prevents that: unsupported operations
    appear in the report's Limitations section.
    """

    requested: NonEmptyStr
    reason: str = ""


class Constraints(JarvisModel):
    """Conditions the run must respect."""

    # The project's default posture. A run with evidence_required=False would be a
    # different product.
    evidence_required: bool = True
    verification_required: bool = True
    max_runtime_s: float | None = Field(default=None, gt=0)
    max_documents: int | None = Field(default=None, ge=1)
    # Minimum computed confidence for a finding to appear as verified in the report.
    min_reportable_confidence: UnitFloat = 0.5


class Intent(JarvisModel):
    """The validated interpretation of an objective."""

    goal: NonEmptyStr = Field(
        description="Short machine-ish identifier, e.g. investigate_project_consistency"
    )
    objective: NonEmptyStr = Field(description="One-sentence restatement of what is wanted")
    required_operations: list[RequiredOperation] = Field(min_length=1)
    unsupported_operations: list[UnsupportedOperation] = Field(default_factory=list)
    constraints: Constraints = Field(default_factory=Constraints)
    output_format: OutputFormat = OutputFormat.INVESTIGATION_REPORT

    # Set when the objective is too vague to plan against. An ambiguous request must not
    # produce a confident plan — guessing is the failure mode here, not the recovery.
    clarification_needed: bool = False
    clarification_question: str = ""

    @field_validator("required_operations")
    @classmethod
    def _no_duplicate_operations(cls, v: list[RequiredOperation]) -> list[RequiredOperation]:
        seen = [op.operation for op in v]
        if len(seen) != len(set(seen)):
            dupes = {op for op in seen if seen.count(op) > 1}
            raise ValueError(f"duplicate operations: {sorted(o.value for o in dupes)}")
        return v

    @model_validator(mode="after")
    def _clarification_needs_a_question(self) -> Intent:
        if self.clarification_needed and not self.clarification_question.strip():
            raise ValueError(
                "clarification_needed=True requires a clarification_question: "
                "telling the user it is unclear without saying what is unclear is useless"
            )
        return self

    @property
    def operations(self) -> list[Operation]:
        return [op.operation for op in self.required_operations]

    @property
    def mandatory_operations(self) -> list[Operation]:
        """Operations the planner must cover. Phase 7 checks coverage against this."""
        return [op.operation for op in self.required_operations if not op.optional]
