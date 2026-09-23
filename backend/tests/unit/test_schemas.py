"""Phase 2 — the typed spine.

These tests do two jobs. The routine one is validation coverage: bounds, enums, round-trips.
The important one is encoding the architectural invariants as executable assertions, so that
a future change which quietly breaks "confidence is computed, never asked for" fails here
rather than in a demo.
"""

from __future__ import annotations

import json

import pytest
from pydantic import ValidationError

from app.schemas import (
    ClaimElement,
    Confidence,
    EventType,
    Evidence,
    EvidenceGap,
    EvidenceRef,
    EvidenceStrength,
    ExecutionEvent,
    ExecutionTrace,
    FinalReport,
    Finding,
    FindingClassification,
    GapType,
    IllegalTransitionError,
    Intent,
    Objective,
    Operation,
    Plan,
    PlanRevision,
    PlanValidationResult,
    PlanViolation,
    RequiredOperation,
    ResolutionStatus,
    RevisionTrigger,
    SourceLocator,
    Task,
    TaskDependency,
    TaskResult,
    TaskStatus,
    TaskType,
    ViolationCode,
    can_transition,
    new_run_id,
)
from app.schemas.common import FailureClass, is_retryable
from app.schemas.verification import (
    IssueType,
    VerificationIssue,
    VerificationResult,
    VerificationStatus,
)

# --- helpers -------------------------------------------------------------------


def _locator(doc: str = "project_report.pdf", page: int = 12) -> SourceLocator:
    return SourceLocator(document_id=doc, document_name=doc, page=page)


def _resolved_ref(doc: str = "project_report.pdf", page: int = 12) -> EvidenceRef:
    return EvidenceRef(locator=_locator(doc, page), resolution=ResolutionStatus.RESOLVED)


def _unresolved_ref(doc: str = "ghost.pdf", page: int = 1) -> EvidenceRef:
    return EvidenceRef(locator=_locator(doc, page))


# --- enum completeness (spec conformance) --------------------------------------


def test_all_eight_task_states_exist() -> None:
    expected = {
        "PENDING",
        "READY",
        "RUNNING",
        "COMPLETED",
        "FAILED",
        "RETRYING",
        "BLOCKED",
        "SKIPPED",
    }
    assert {s.value for s in TaskStatus} == expected


def test_all_four_classifications_exist() -> None:
    assert {c.value for c in FindingClassification} == {
        "FACT",
        "INFERENCE",
        "HYPOTHESIS",
        "UNKNOWN",
    }


@pytest.mark.parametrize(
    "required",
    [
        "RUN_STARTED",
        "INTENT_CREATED",
        "PLAN_CREATED",
        "TASK_GRAPH_CREATED",
        "TASK_STARTED",
        "TASK_COMPLETED",
        "REASONING_STARTED",
        "VERIFICATION_STARTED",
        "FINDING_VERIFIED",
        "EVIDENCE_GAP_DETECTED",
        "REPLAN_STARTED",
        "TASK_CREATED",
        "REASONING_REVISED",
        "VERIFICATION_COMPLETED",
        "SYNTHESIS_COMPLETED",
        "RUN_COMPLETED",
    ],
)
def test_specified_event_types_exist(required: str) -> None:
    """Every event named in the specification's sample trace must be emittable."""
    assert required in {e.value for e in EventType}


def test_every_task_type_maps_to_a_capability_and_operations() -> None:
    """A task type nothing can route or plan for is a latent runtime failure."""
    from app.schemas import TASK_CAPABILITY, TASK_SATISFIES

    for task_type in TaskType:
        assert task_type in TASK_CAPABILITY, f"{task_type} has no capability mapping"
        assert TASK_SATISFIES.get(task_type), f"{task_type} satisfies no operation"


def test_every_operation_is_satisfiable_by_some_task_type() -> None:
    """The planner cannot cover an operation no task type implements."""
    from app.schemas import TASK_SATISFIES

    satisfiable: set[Operation] = set()
    for ops in TASK_SATISFIES.values():
        satisfiable |= ops
    missing = set(Operation) - satisfiable
    assert not missing, f"operations with no implementing task type: {missing}"


# --- Confidence: computed, never declared --------------------------------------


def test_confidence_cannot_be_conjured_from_a_bare_number() -> None:
    """The architectural invariant, enforced by the type.

    There is no constructor that takes only a value. A model's self-reported certainty has
    nowhere to go.
    """
    with pytest.raises(ValidationError):
        Confidence(value=0.96)  # type: ignore[call-arg]


def test_confidence_is_zero_without_resolved_evidence() -> None:
    c = Confidence.compute(refs=[_unresolved_ref()], classification=FindingClassification.FACT)
    assert c.value == 0.0
    assert c.resolution_rate == 0.0


def test_confidence_is_capped_by_classification() -> None:
    """Perfect evidence on a HYPOTHESIS still cannot present as near-certain."""
    refs = [_resolved_ref(), _resolved_ref("financial_report.pdf", 4)]
    hypothesis = Confidence.compute(refs=refs, classification=FindingClassification.HYPOTHESIS)
    fact = Confidence.compute(refs=refs, classification=FindingClassification.FACT)

    assert hypothesis.value <= 0.4
    assert fact.value > hypothesis.value


def test_confidence_falls_with_partial_resolution() -> None:
    full = Confidence.compute(
        refs=[_resolved_ref(), _resolved_ref("b.pdf", 2)],
        classification=FindingClassification.FACT,
    )
    partial = Confidence.compute(
        refs=[_resolved_ref(), _unresolved_ref()],
        classification=FindingClassification.FACT,
    )
    assert partial.value < full.value


def test_contradictory_evidence_scores_zero_strength() -> None:
    c = Confidence.compute(
        refs=[_resolved_ref()],
        strengths=[EvidenceStrength.CONTRADICTORY],
        classification=FindingClassification.FACT,
    )
    assert c.value == 0.0


def test_confidence_is_reproducible() -> None:
    """A pure function of evidence. Phase 20 depends on this being measurable, not noisy."""
    refs = [_resolved_ref(), _unresolved_ref()]
    a = Confidence.compute(refs=refs, classification=FindingClassification.INFERENCE)
    b = Confidence.compute(refs=refs, classification=FindingClassification.INFERENCE)
    assert a.value == b.value


def test_confidence_explains_itself() -> None:
    c = Confidence.compute(refs=[_resolved_ref()], classification=FindingClassification.FACT)
    explanation = c.explain()
    assert "resolved" in explanation and "strength" in explanation
    assert explanation.isascii(), "operator output must be ASCII (BUG-001)"


# --- Finding invariants --------------------------------------------------------


def test_a_fact_requires_resolved_evidence() -> None:
    """The invariant the whole architecture exists to protect."""
    with pytest.raises(ValidationError, match="FACT requires at least one resolved"):
        Finding(
            finding_id="F-001",
            claim="The completion dates conflict.",
            classification=FindingClassification.FACT,
            evidence=[_unresolved_ref()],
        )


def test_confidence_exceeding_its_classification_ceiling_is_rejected() -> None:
    inflated = Confidence.compute(refs=[_resolved_ref()], classification=FindingClassification.FACT)
    with pytest.raises(ValidationError, match="exceeds the ceiling"):
        Finding(
            finding_id="F-002",
            claim="Possibly delayed.",
            classification=FindingClassification.HYPOTHESIS,
            evidence=[_resolved_ref()],
            confidence=inflated,
        )


def test_classification_is_recomputed_from_evidence_not_trusted() -> None:
    """A claim asserting FACT while carrying an unresolved citation is a HYPOTHESIS."""
    f = Finding(
        finding_id="F-003",
        claim="The project slipped two weeks.",
        classification=FindingClassification.UNKNOWN,
        evidence=[_resolved_ref(), _unresolved_ref()],
    )
    assert f.classify() is FindingClassification.HYPOTHESIS


def test_two_independent_sources_yield_an_inference() -> None:
    f = Finding(
        finding_id="F-004",
        claim="Budget and timeline disagree.",
        evidence=[_resolved_ref("a.pdf", 1), _resolved_ref("b.pdf", 2)],
        elements=[ClaimElement(text="disagreement", supported=False)],
    )
    assert f.classify() is FindingClassification.INFERENCE


def test_contradicted_finding_is_rejected_not_merely_unverified() -> None:
    """More evidence cannot rescue a claim the sources refute."""
    f = Finding(
        finding_id="F-005",
        claim="Spend is under budget.",
        evidence=[_resolved_ref()],
        verification=VerificationResult(
            status=VerificationStatus.CONTRADICTED,
            confidence=0.9,
            issues=[
                VerificationIssue(
                    issue_type=IssueType.EVIDENCE_MISMATCH,
                    description="Cited figure shows an overrun.",
                )
            ],
        ),
    )
    assert f.is_rejected
    assert not f.is_verified
    assert not f.needs_investigation, "a contradicted claim is not a gap to fill"


def test_unsupported_finding_with_a_gap_needs_investigation() -> None:
    f = Finding(
        finding_id="F-006",
        claim="The project slipped against baseline.",
        evidence=[_resolved_ref()],
        gaps=[
            EvidenceGap(
                gap_id="G-001",
                finding_id="F-006",
                gap_type=GapType.MISSING_BASELINE,
                missing="approved baseline completion date",
            )
        ],
        verification=VerificationResult(
            status=VerificationStatus.PARTIALLY_SUPPORTED,
            confidence=0.5,
            issues=[
                VerificationIssue(
                    issue_type=IssueType.NO_EVIDENCE,
                    description="No baseline schedule cited.",
                )
            ],
        ),
    )
    assert f.needs_investigation
    assert len(f.unresolved_gaps) == 1


# --- Verification contract -----------------------------------------------------


def test_a_rejection_must_state_a_reason() -> None:
    """A status with no issue cannot be acted on by the replanning loop."""
    with pytest.raises(ValidationError, match="requires at least one issue"):
        VerificationResult(status=VerificationStatus.UNSUPPORTED, confidence=0.2)


def test_degraded_verification_must_say_why() -> None:
    with pytest.raises(ValidationError, match="degraded_reason"):
        VerificationResult(status=VerificationStatus.SUPPORTED, confidence=0.9, degraded=True)


def test_contradicted_is_not_actionable_but_unsupported_is() -> None:
    issue = VerificationIssue(issue_type=IssueType.NO_EVIDENCE, description="nothing cited")
    contradicted = VerificationResult(
        status=VerificationStatus.CONTRADICTED, confidence=0.9, issues=[issue]
    )
    unsupported = VerificationResult(
        status=VerificationStatus.UNSUPPORTED, confidence=0.2, issues=[issue]
    )
    assert not contradicted.actionable
    assert unsupported.actionable


def test_verification_request_carries_no_reasoning_trail() -> None:
    """Independence is the contract, so the field must not exist."""
    from app.schemas.verification import VerificationRequest

    fields = set(VerificationRequest.model_fields)
    forbidden = {"reasoning", "reasoning_trace", "chain_of_thought", "observations", "plan"}
    assert not (fields & forbidden), (
        "VerificationRequest must not expose the reasoning that produced the claim"
    )


# --- Evidence gaps -------------------------------------------------------------


def test_a_resolved_gap_must_name_the_task_that_closed_it() -> None:
    with pytest.raises(ValidationError, match="must name the task"):
        EvidenceGap(
            gap_id="G-002",
            finding_id="F-001",
            gap_type=GapType.MISSING_SOURCE,
            missing="signed contract amendment",
            resolved=True,
        )


def test_gap_missing_field_cannot_be_empty() -> None:
    """'More evidence needed' is not a gap. A gap names an element."""
    with pytest.raises(ValidationError):
        EvidenceGap(
            gap_id="G-003",
            finding_id="F-001",
            gap_type=GapType.MISSING_BASELINE,
            missing="",
        )


def test_evidence_converts_to_a_resolved_ref() -> None:
    ev = Evidence(
        evidence_id="E-001",
        locator=_locator(),
        content="Target completion 2026-04-30.",
    )
    ref = ev.to_ref()
    assert ref.is_resolved
    assert ref.evidence_id == "E-001"


# --- Task state machine --------------------------------------------------------


def test_legal_transition_path() -> None:
    t = Task(task_id="task_001", task_type=TaskType.EXTRACT_TIMELINE, description="extract")
    t.transition_to(TaskStatus.READY)
    t.transition_to(TaskStatus.RUNNING)
    t.transition_to(TaskStatus.COMPLETED)
    assert t.is_terminal
    assert t.started_at is not None and t.completed_at is not None


def test_a_task_cannot_complete_without_running() -> None:
    """The bug that would produce a report built on work that never happened."""
    t = Task(task_id="task_002", task_type=TaskType.EXTRACT_BUDGET, description="extract")
    with pytest.raises(IllegalTransitionError):
        t.transition_to(TaskStatus.COMPLETED)


def test_completed_is_terminal() -> None:
    assert not can_transition(TaskStatus.COMPLETED, TaskStatus.RUNNING)
    assert not can_transition(TaskStatus.SKIPPED, TaskStatus.READY)


def test_failed_tasks_may_retry_or_be_skipped() -> None:
    assert can_transition(TaskStatus.FAILED, TaskStatus.RETRYING)
    assert can_transition(TaskStatus.FAILED, TaskStatus.SKIPPED)
    assert not can_transition(TaskStatus.FAILED, TaskStatus.COMPLETED)


def test_task_rejects_self_dependency() -> None:
    with pytest.raises(ValidationError, match="itself"):
        Task(
            task_id="task_003",
            task_type=TaskType.COMPARE_SOURCES,
            description="compare",
            depends_on=["task_003"],
        )


def test_dependency_edge_rejects_self_reference() -> None:
    with pytest.raises(ValidationError, match="cannot depend on itself"):
        TaskDependency(task_id="task_004", depends_on_task_id="task_004")


def test_failed_task_result_must_be_classified() -> None:
    """Retry policy cannot distinguish transient from permanent without this."""
    with pytest.raises(ValidationError, match="failure_class"):
        TaskResult(task_id="task_005", ok=False)


@pytest.mark.parametrize(
    ("failure", "retryable"),
    [
        (FailureClass.TIMEOUT, True),
        (FailureClass.CONNECTION_ERROR, True),
        (FailureClass.SCHEMA_VIOLATION, False),
        (FailureClass.UNSAFE_EXPRESSION, False),
        (FailureClass.NO_CAPABLE_TOOL, False),
    ],
)
def test_retryability_classification(failure: FailureClass, retryable: bool) -> None:
    assert is_retryable(failure) is retryable


# --- Plans ---------------------------------------------------------------------


def _task(n: int, ttype: TaskType, deps: list[str] | None = None) -> Task:
    return Task(
        task_id=f"task_{n:03d}",
        task_type=ttype,
        description=ttype.value,
        depends_on=deps or [],
    )


def test_plan_rejects_dependency_on_an_unknown_task() -> None:
    with pytest.raises(ValidationError, match="unknown task"):
        Plan(
            tasks=[_task(1, TaskType.EXTRACT_TIMELINE)],
            dependencies=[TaskDependency(task_id="task_001", depends_on_task_id="task_999")],
        )


def test_plan_rejects_duplicate_task_ids() -> None:
    with pytest.raises(ValidationError, match="duplicate task ids"):
        Plan(tasks=[_task(1, TaskType.EXTRACT_TIMELINE), _task(1, TaskType.EXTRACT_BUDGET)])


def test_plan_reports_covered_operations_and_edges() -> None:
    plan = Plan(
        tasks=[
            _task(1, TaskType.EXTRACT_TIMELINE),
            _task(2, TaskType.EXTRACT_BUDGET),
            _task(3, TaskType.COMPARE_SOURCES, ["task_001", "task_002"]),
        ],
        dependencies=[
            TaskDependency(task_id="task_003", depends_on_task_id="task_001"),
            TaskDependency(task_id="task_003", depends_on_task_id="task_002"),
        ],
    )
    assert Operation.EXTRACT_TIMELINE in plan.covered_operations
    assert ("task_001", "task_003") in plan.edges()


def test_clean_distinguishes_a_good_plan_from_a_rescued_one() -> None:
    """Phase 20 counts `clean`, not `valid`. A plan valid after three repairs is rescued."""
    from app.schemas import PlanRepair, RepairAction

    rescued = PlanValidationResult(
        valid=True,
        repairs=[PlanRepair(action=RepairAction.BROKE_SELF_LOOP)],
        reprompt_count=1,
    )
    pristine = PlanValidationResult(valid=True)
    assert pristine.clean
    assert not rescued.clean


def test_an_invalid_plan_must_record_a_violation() -> None:
    with pytest.raises(ValidationError, match="at least one violation"):
        PlanValidationResult(valid=False)


def test_cycle_violation_carries_the_offending_path() -> None:
    v = PlanViolation(
        code=ViolationCode.CYCLE,
        message="cycle detected",
        path=["task_004", "task_006", "task_004"],
    )
    assert v.path[0] == v.path[-1]


def test_a_revision_that_changes_nothing_is_rejected() -> None:
    with pytest.raises(ValidationError, match="changes nothing"):
        PlanRevision(
            revision=1,
            trigger=RevisionTrigger.EVIDENCE_GAP,
            reason="looked again",
        )


# --- Events and traces ---------------------------------------------------------


def test_events_are_immutable() -> None:
    """An append-only log that can be rewritten is not a record."""
    e = ExecutionEvent(run_id=new_run_id(), event_type=EventType.RUN_STARTED, t_offset_ms=0)
    with pytest.raises(ValidationError):
        e.event_type = EventType.RUN_FAILED  # type: ignore[misc]


def test_model_deliberation_is_stripped_before_persistence() -> None:
    """Invariant #3, at its enforcement point."""
    e = ExecutionEvent(
        run_id=new_run_id(),
        event_type=EventType.FINDING_CREATED,
        t_offset_ms=5800,
        payload={
            "finding_id": "F-001",
            "raw_response": "let me think step by step...",
            "chain_of_thought": "first I considered...",
        },
    )
    clean = e.redacted()
    assert "finding_id" in clean.payload
    assert "raw_response" not in clean.payload
    assert "chain_of_thought" not in clean.payload


def test_offset_renders_as_the_trace_timeline_format() -> None:
    e = ExecutionEvent(run_id=new_run_id(), event_type=EventType.FINDING_VERIFIED, t_offset_ms=6900)
    assert e.offset_display == "00:06.900"
    assert e.describe().isascii()


def test_trace_ordered_containment_is_the_core_scenario_assertion() -> None:
    """Scenarios prove the agent did the work by asserting on event order."""
    run = new_run_id()
    trace = ExecutionTrace(
        run_id=run,
        objective="Find inconsistencies.",
        events=[
            ExecutionEvent(run_id=run, event_type=EventType.RUN_STARTED, t_offset_ms=0),
            ExecutionEvent(
                run_id=run, event_type=EventType.EVIDENCE_GAP_DETECTED, t_offset_ms=6900
            ),
            ExecutionEvent(run_id=run, event_type=EventType.REPLAN_STARTED, t_offset_ms=7000),
            ExecutionEvent(run_id=run, event_type=EventType.TASK_CREATED, t_offset_ms=7050),
            ExecutionEvent(run_id=run, event_type=EventType.RUN_COMPLETED, t_offset_ms=9520),
        ],
    )
    assert trace.contains_ordered(
        [EventType.EVIDENCE_GAP_DETECTED, EventType.REPLAN_STARTED, EventType.TASK_CREATED]
    )
    # Order matters: replanning cannot precede the gap that caused it.
    assert not trace.contains_ordered(
        [EventType.REPLAN_STARTED, EventType.EVIDENCE_GAP_DETECTED, EventType.TASK_CREATED]
    )
    assert trace.duration_ms == 9520


def test_event_filter_supports_sse_replay() -> None:
    run = new_run_id()
    early = ExecutionEvent(run_id=run, event_type=EventType.RUN_STARTED, t_offset_ms=0)
    late = ExecutionEvent(run_id=run, event_type=EventType.TASK_STARTED, t_offset_ms=1300)
    from app.schemas import EventFilter

    f = EventFilter(run_id=run, after_offset_ms=500)
    assert not f.matches(early)
    assert f.matches(late)


# --- Report contract -----------------------------------------------------------


def test_report_refuses_to_present_unsupported_claims_as_verified() -> None:
    """The last line of defence before a human reads the output."""
    unsupported = Finding(
        finding_id="F-010",
        claim="Spending exceeded the approved budget.",
        evidence=[_unresolved_ref()],
    )
    with pytest.raises(ValidationError, match="without resolved evidence"):
        FinalReport(
            run_id=new_run_id(),
            objective="Audit the project.",
            verified_findings=[unsupported],
        )


def test_report_has_a_section_for_rejected_findings() -> None:
    """A report showing only what survived is a highlight reel, not an audit."""
    from app.schemas import SectionKind

    assert SectionKind.REJECTED_FINDINGS in set(SectionKind)
    assert SectionKind.UNCERTAIN_FINDINGS in set(SectionKind)
    assert SectionKind.LIMITATIONS in set(SectionKind)


def test_all_eleven_specified_sections_exist() -> None:
    from app.schemas import REQUIRED_SECTIONS

    assert len(REQUIRED_SECTIONS) == 11


def test_successful_result_requires_a_report() -> None:
    from app.schemas import AgentResult, RunStatus

    with pytest.raises(ValidationError, match="requires a report"):
        AgentResult(run_id=new_run_id(), status=RunStatus.COMPLETED)


def test_failed_result_requires_an_error_code() -> None:
    from app.schemas import AgentResult, RunStatus

    with pytest.raises(ValidationError, match="error_code"):
        AgentResult(run_id=new_run_id(), status=RunStatus.FAILED)


# --- Intent --------------------------------------------------------------------


def test_intent_rejects_duplicate_operations() -> None:
    with pytest.raises(ValidationError, match="duplicate operations"):
        Intent(
            goal="investigate_consistency",
            objective="Check consistency.",
            required_operations=[
                RequiredOperation(operation=Operation.COMPARE_SOURCES),
                RequiredOperation(operation=Operation.COMPARE_SOURCES),
            ],
        )


def test_clarification_must_come_with_a_question() -> None:
    """Telling the user it is unclear without saying what is unclear is useless."""
    with pytest.raises(ValidationError, match="clarification_question"):
        Intent(
            goal="unclear",
            objective="Look at these files.",
            required_operations=[RequiredOperation(operation=Operation.SUMMARIZE)],
            clarification_needed=True,
        )


def test_mandatory_operations_exclude_optional_ones() -> None:
    intent = Intent(
        goal="investigate_consistency",
        objective="Check timeline against budget.",
        required_operations=[
            RequiredOperation(operation=Operation.EXTRACT_TIMELINE),
            RequiredOperation(operation=Operation.ASSESS_IMPACT, optional=True),
        ],
    )
    assert Operation.ASSESS_IMPACT in intent.operations
    assert Operation.ASSESS_IMPACT not in intent.mandatory_operations


# --- Structural guarantees -----------------------------------------------------


def test_unknown_fields_are_rejected() -> None:
    """These models parse LLM output. An invented field must trigger the repair loop,
    not be silently dropped into a plausible-looking object."""
    with pytest.raises(ValidationError):
        SourceLocator(document_id="a.pdf", invented_field="surprise")  # type: ignore[call-arg]


@pytest.mark.parametrize(
    "model",
    [
        Objective(text="Find inconsistencies."),
        Intent(
            goal="g",
            objective="o",
            required_operations=[RequiredOperation(operation=Operation.SUMMARIZE)],
        ),
        Task(task_id="task_001", task_type=TaskType.SUMMARIZE, description="d"),
        Finding(finding_id="F-001", claim="c"),
        EvidenceGap(
            gap_id="G-001",
            finding_id="F-001",
            gap_type=GapType.MISSING_SOURCE,
            missing="the contract",
        ),
        ExecutionEvent(run_id="run_0123456789ab", event_type=EventType.RUN_STARTED, t_offset_ms=0),
    ],
)
def test_json_round_trip_is_lossless(model: object) -> None:
    assert hasattr(model, "model_dump_json")
    dumped = model.model_dump_json()  # type: ignore[attr-defined]
    restored = type(model).model_validate(json.loads(dumped))  # type: ignore[attr-defined]
    assert restored == model


def test_schemas_package_imports_no_engine_code() -> None:
    """Invariant #2: the typed spine is the contract, not a consequence of the code.

    Importing schemas must not drag in a provider, a database session or an engine.
    """
    import subprocess
    import sys

    result = subprocess.run(
        [
            sys.executable,
            "-c",
            "import sys; import app.schemas; "
            "bad=[m for m in sys.modules if m.startswith('app.') "
            "and not m.startswith('app.schemas') and m!='app']; "
            "print(bad)",
        ],
        capture_output=True,
        text=True,
        check=True,
    )
    assert result.stdout.strip() == "[]", f"schemas pulled in {result.stdout.strip()}"


def test_source_locator_renders_a_compact_reference() -> None:
    assert _locator().as_ref() == "project_report.pdf:p12"
