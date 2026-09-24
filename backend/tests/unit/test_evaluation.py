"""Phase 20 — the evaluation harness.

The scorers are pure functions, so they can be tested exactly. That matters more here than
anywhere else in the project: every claim about how well the agent works is these functions'
output, and a scorer that flatters the system would be worse than having no metrics at all.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.evaluation.metrics import (
    MetricSet,
    ScenarioExpectation,
    ScenarioOutcome,
    aggregate,
    claims_found,
    dependency_correctness,
    deterministic_routing_share,
    evidence_coverage,
    intent_accuracy,
    negative_case_score,
    plan_validity,
    replanning_success,
    score_scenario,
    task_efficiency,
    tool_selection_accuracy,
    unsupported_claim_rate,
    verification_success,
)
from app.evaluation.report import (
    EvalReport,
    ScenarioReport,
    compare,
    config_hash,
    load_latest,
    to_markdown,
    write_report,
)
from app.evaluation.runner import load_expectations
from app.schemas.common import SourceLocator
from app.schemas.evidence import EvidenceGap, EvidenceRef, GapType, ResolutionStatus
from app.schemas.finding import Confidence, Finding, FindingClassification
from app.schemas.intent import Intent, Operation, RequiredOperation
from app.schemas.plan import Plan, PlanRepair, PlanValidationResult, RepairAction
from app.schemas.task import Task, TaskDependency, TaskStatus, TaskType
from app.schemas.tool import SelectionMode, ToolCapability, ToolSelection
from app.schemas.verification import (
    IssueType,
    VerificationIssue,
    VerificationResult,
    VerificationStatus,
)


def _ref(doc: str = "a.txt", *, resolved: bool = True) -> EvidenceRef:
    return EvidenceRef(
        locator=SourceLocator(document_id=doc, document_name=doc, row=1),
        resolution=ResolutionStatus.RESOLVED if resolved else ResolutionStatus.UNRESOLVED,
        resolution_note="" if resolved else "no task produced this locator",
    )


def _finding(
    fid: str = "F-001",
    *,
    claim: str = "The dates conflict.",
    resolved: bool = True,
    status: VerificationStatus | None = VerificationStatus.SUPPORTED,
) -> Finding:
    refs = [_ref(resolved=resolved)]
    classification = FindingClassification.FACT if resolved else FindingClassification.UNKNOWN
    verification = None
    if status is not None:
        issues = (
            []
            if status is VerificationStatus.SUPPORTED
            else [VerificationIssue(issue_type=IssueType.NO_EVIDENCE, description="none")]
        )
        verification = VerificationResult(status=status, confidence=0.8, issues=issues)
    return Finding(
        finding_id=fid,
        claim=claim,
        classification=classification,
        evidence=refs,
        confidence=Confidence.compute(refs=refs, classification=classification),
        verification=verification,
    )


def _task(n: int, ttype: TaskType, deps: list[str] | None = None, *, tool: str = "") -> Task:
    return Task(
        task_id=f"task_{n:03d}",
        task_type=ttype,
        description=ttype.value,
        depends_on=deps or [],
        status=TaskStatus.COMPLETED,
        selection=(
            ToolSelection(
                tool_name=tool,
                capability=ToolCapability.DOCUMENT_EXTRACT,
                mode=SelectionMode.DETERMINISTIC,
            )
            if tool
            else None
        ),
    )


def _plan(*, clean: bool = True, tasks: list[Task] | None = None) -> Plan:
    tasks = tasks or [
        _task(1, TaskType.EXTRACT_TIMELINE, tool="document_extract"),
        _task(2, TaskType.EXTRACT_BUDGET, tool="document_extract"),
        _task(3, TaskType.COMPARE_SOURCES, ["task_001", "task_002"]),
        _task(4, TaskType.SYNTHESIZE, ["task_003"]),
    ]
    validation = PlanValidationResult(
        valid=True,
        repairs=[] if clean else [PlanRepair(action=RepairAction.BROKE_SELF_LOOP)],
    )
    dependencies = [
        TaskDependency(task_id=t.task_id, depends_on_task_id=d) for t in tasks for d in t.depends_on
    ]
    return Plan(tasks=tasks, dependencies=dependencies, validation=validation)


def _intent(*ops: Operation) -> Intent:
    return Intent(
        goal="g",
        objective="o",
        required_operations=[RequiredOperation(operation=op) for op in ops]
        or [RequiredOperation(operation=Operation.SUMMARIZE)],
    )


def _expectation(**kwargs: object) -> ScenarioExpectation:
    base: dict[str, object] = {"scenario_id": "s1", "objective": "o"}
    base.update(kwargs)
    return ScenarioExpectation.model_validate(base)


# --- intent accuracy -----------------------------------------------------------


def test_a_perfect_intent_scores_one() -> None:
    expectation = _expectation(expected_operations=[Operation.EXTRACT_TIMELINE])
    outcome = ScenarioOutcome(scenario_id="s1", intent=_intent(Operation.EXTRACT_TIMELINE))
    assert intent_accuracy(expectation, outcome) == pytest.approx(1.0)


def test_requesting_every_operation_does_not_score_well() -> None:
    """F1 rather than recall: an intent that asks for everything is useless."""
    expectation = _expectation(expected_operations=[Operation.EXTRACT_TIMELINE])
    outcome = ScenarioOutcome(scenario_id="s1", intent=_intent(*list(Operation)))
    assert intent_accuracy(expectation, outcome) < 0.5


def test_a_missing_intent_scores_zero() -> None:
    expectation = _expectation(expected_operations=[Operation.EXTRACT_TIMELINE])
    assert intent_accuracy(expectation, ScenarioOutcome(scenario_id="s1")) == 0.0


# --- plan validity -------------------------------------------------------------


def test_a_clean_plan_scores_one() -> None:
    assert plan_validity(ScenarioOutcome(scenario_id="s1", plan=_plan())) == 1.0


def test_a_rescued_plan_does_not_count_as_valid() -> None:
    """Counting repairs as success would let the planner degrade while the metric held."""
    assert plan_validity(ScenarioOutcome(scenario_id="s1", plan=_plan(clean=False))) == 0.0


def test_no_plan_scores_zero() -> None:
    assert plan_validity(ScenarioOutcome(scenario_id="s1")) == 0.0


# --- dependency correctness ----------------------------------------------------


def test_matching_edges_score_one() -> None:
    expectation = _expectation(
        expected_edges=[
            ("extract_timeline", "compare_sources"),
            ("extract_budget", "compare_sources"),
            ("compare_sources", "synthesize"),
        ]
    )
    outcome = ScenarioOutcome(scenario_id="s1", plan=_plan())
    assert dependency_correctness(expectation, outcome) == pytest.approx(1.0)


def test_edges_are_compared_by_task_type_not_id() -> None:
    """Task ids vary between runs; comparing them would measure numbering, not structure."""
    expectation = _expectation(expected_edges=[("extract_timeline", "compare_sources")])
    renumbered = [
        _task(90, TaskType.EXTRACT_TIMELINE),
        _task(91, TaskType.COMPARE_SOURCES, ["task_090"]),
    ]
    outcome = ScenarioOutcome(scenario_id="s1", plan=_plan(tasks=renumbered))
    assert dependency_correctness(expectation, outcome) > 0.0


def test_a_wrong_dag_scores_zero() -> None:
    expectation = _expectation(expected_edges=[("extract_budget", "assess_impact")])
    outcome = ScenarioOutcome(scenario_id="s1", plan=_plan())
    assert dependency_correctness(expectation, outcome) == 0.0


# --- tool selection ------------------------------------------------------------


def test_correct_routing_scores_one() -> None:
    expectation = _expectation(expected_tools={"extract_timeline": "document_extract"})
    outcome = ScenarioOutcome(scenario_id="s1", plan=_plan())
    assert tool_selection_accuracy(expectation, outcome) == 1.0


def test_wrong_routing_scores_zero() -> None:
    expectation = _expectation(expected_tools={"extract_timeline": "calculator"})
    outcome = ScenarioOutcome(scenario_id="s1", plan=_plan())
    assert tool_selection_accuracy(expectation, outcome) == 0.0


def test_the_deterministic_share_is_reported() -> None:
    """A falling share means the capability model stopped discriminating."""
    outcome = ScenarioOutcome(scenario_id="s1", plan=_plan())
    assert deterministic_routing_share(outcome) == 1.0


# --- evidence and the headline metric ------------------------------------------


def test_coverage_counts_findings_with_resolved_evidence() -> None:
    outcome = ScenarioOutcome(
        scenario_id="s1",
        findings=[_finding("F-001"), _finding("F-002", resolved=False)],
    )
    assert evidence_coverage(outcome) == pytest.approx(0.5)


def test_an_empty_result_is_not_punished_on_coverage() -> None:
    """A correct empty result would otherwise score as poor coverage."""
    assert evidence_coverage(ScenarioOutcome(scenario_id="s1")) == 1.0


def test_the_unsupported_claim_rate_counts_claims_with_no_resolved_evidence() -> None:
    outcome = ScenarioOutcome(
        scenario_id="s1",
        findings=[_finding("F-001"), _finding("F-002", resolved=False)],
    )
    assert unsupported_claim_rate(outcome) == pytest.approx(0.5)


def test_asserting_nothing_has_a_zero_unsupported_rate() -> None:
    assert unsupported_claim_rate(ScenarioOutcome(scenario_id="s1")) == 0.0


def test_the_unsupported_rate_is_the_only_build_failing_metric() -> None:
    from app.evaluation.report import FAIL_BUILD_ABOVE

    assert set(FAIL_BUILD_ABOVE) == {"unsupported_claim_rate"}


# --- verification and replanning -----------------------------------------------


def test_verification_success_is_the_share_that_survived() -> None:
    outcome = ScenarioOutcome(
        scenario_id="s1",
        findings=[
            _finding("F-001"),
            _finding("F-002", status=VerificationStatus.UNSUPPORTED),
        ],
    )
    assert verification_success(outcome) == pytest.approx(0.5)


def test_replanning_success_is_the_share_of_gaps_closed() -> None:
    gaps = [
        EvidenceGap(
            gap_id="G-001",
            finding_id="F-001",
            gap_type=GapType.MISSING_SOURCE,
            missing="a source",
            resolved=True,
            resolved_by_task_id="task_009",
        ),
        EvidenceGap(
            gap_id="G-002",
            finding_id="F-001",
            gap_type=GapType.MISSING_BASELINE,
            missing="a baseline",
        ),
    ]
    assert replanning_success(ScenarioOutcome(scenario_id="s1", gaps=gaps)) == pytest.approx(0.5)


def test_detecting_no_gaps_scores_one() -> None:
    assert replanning_success(ScenarioOutcome(scenario_id="s1")) == 1.0


# --- negative cases ------------------------------------------------------------


def test_a_negative_case_passes_when_nothing_is_found() -> None:
    """An agent that always finds something is confabulating, not investigating."""
    expectation = _expectation(expect_zero_findings=True)
    assert negative_case_score(expectation, ScenarioOutcome(scenario_id="s1")) == 1.0


def test_a_negative_case_fails_when_something_is_invented() -> None:
    expectation = _expectation(expect_zero_findings=True)
    outcome = ScenarioOutcome(scenario_id="s1", findings=[_finding()])
    assert negative_case_score(expectation, outcome) == 0.0


def test_claims_are_matched_loosely() -> None:
    """Two correct phrasings of the same contradiction are both correct."""
    expectation = _expectation(expected_claims=["dates conflict"])
    outcome = ScenarioOutcome(
        scenario_id="s1", findings=[_finding(claim="The completion DATES CONFLICT badly.")]
    )
    assert claims_found(expectation, outcome) == 1.0


# --- efficiency and aggregation ------------------------------------------------


def test_efficiency_is_executed_over_minimal() -> None:
    expectation = _expectation(minimal_tasks=2)
    outcome = ScenarioOutcome(scenario_id="s1", plan=_plan())
    assert task_efficiency(expectation, outcome) == pytest.approx(2.0)


def test_aggregation_is_an_unweighted_mean() -> None:
    """Weighting by size would let one big scenario hide a regression in everything else."""
    a = MetricSet(evidence_coverage=1.0)
    b = MetricSet(evidence_coverage=0.0)
    assert aggregate([a, b]).evidence_coverage == pytest.approx(0.5)


def test_aggregating_nothing_yields_zeros() -> None:
    assert aggregate([]).evidence_coverage == 0.0


def test_scoring_a_scenario_produces_all_ten_metrics() -> None:
    metrics = score_scenario(
        _expectation(), ScenarioOutcome(scenario_id="s1", plan=_plan(), findings=[_finding()])
    )
    assert len(metrics.as_dict()) == 10


# --- regression detection ------------------------------------------------------


def _report(**metrics: float) -> EvalReport:
    return EvalReport(
        suite="core",
        model="qwen3:4b",
        prompt_versions={"reasoning": 1},
        config_hash="sha256:abc",
        aggregate=MetricSet.model_validate(metrics),
    )


def test_a_drop_beyond_tolerance_is_a_regression() -> None:
    result = compare(
        _report(evidence_coverage=0.90),
        _report(evidence_coverage=0.70),
        {"evidence_coverage": 0.05},
    )
    assert not result.passed
    assert [d.metric for d in result.regressions] == ["evidence_coverage"]


def test_a_small_drop_within_tolerance_passes() -> None:
    result = compare(
        _report(evidence_coverage=0.90),
        _report(evidence_coverage=0.88),
        {"evidence_coverage": 0.05},
    )
    assert result.passed


def test_direction_is_respected_for_lower_is_better_metrics() -> None:
    """A rising unsupported-claim rate is a regression, not an improvement."""
    result = compare(
        _report(unsupported_claim_rate=0.02),
        _report(unsupported_claim_rate=0.30),
        {"unsupported_claim_rate": 0.02},
    )
    assert [d.metric for d in result.regressions] == ["unsupported_claim_rate"]


def test_an_unexplained_improvement_is_flagged() -> None:
    """A metric that jumps without a cause usually means the measurement broke."""
    result = compare(
        _report(evidence_coverage=0.30),
        _report(evidence_coverage=0.99),
        {"evidence_coverage": 0.05},
    )
    assert [d.metric for d in result.unexplained_improvements] == ["evidence_coverage"]


def test_reports_from_different_models_are_not_compared() -> None:
    """The numbers would describe different systems."""
    baseline = _report(evidence_coverage=0.9)
    current = _report(evidence_coverage=0.5).model_copy(update={"model": "llama3.1:8b"})

    result = compare(baseline, current, {})
    assert not result.comparable
    assert "different model" in result.reason
    assert result.regressions == [], "no regression is claimed across incomparable runs"


def test_reports_from_different_prompt_versions_are_not_compared() -> None:
    baseline = _report(evidence_coverage=0.9)
    current = _report(evidence_coverage=0.5).model_copy(
        update={"prompt_versions": {"reasoning": 2}}
    )
    assert not compare(baseline, current, {}).comparable


def test_the_config_hash_is_stable_and_sensitive() -> None:
    assert config_hash({"a": 1}) == config_hash({"a": 1})
    assert config_hash({"a": 1}) != config_hash({"a": 2})


# --- build thresholds ----------------------------------------------------------


def test_a_high_unsupported_rate_fails_the_build() -> None:
    assert _report(unsupported_claim_rate=0.40).build_failures()


def test_an_acceptable_unsupported_rate_passes() -> None:
    assert _report(unsupported_claim_rate=0.05).build_failures() == []


# --- report rendering and round-trip -------------------------------------------


def test_the_markdown_report_states_that_nothing_is_hard_coded() -> None:
    report = _report(evidence_coverage=0.9)
    report.scenarios.append(ScenarioReport(scenario_id="s1", metrics=MetricSet()))
    markdown = to_markdown(report)

    assert "computed from real runs" in markdown
    assert "unsupported_claim_rate" in markdown
    assert markdown.isascii()


def test_a_written_report_reloads_as_the_latest_baseline(tmp_path: Path) -> None:
    report = _report(evidence_coverage=0.9)
    json_path, md_path = write_report(report, tmp_path)

    assert json_path.exists() and md_path.exists()
    reloaded = load_latest(tmp_path, "core")
    assert reloaded is not None
    assert reloaded.aggregate.evidence_coverage == pytest.approx(0.9)


def test_no_baseline_returns_none(tmp_path: Path) -> None:
    assert load_latest(tmp_path, "core") is None


def test_a_report_round_trips_through_json() -> None:
    report = _report(evidence_coverage=0.9)
    assert EvalReport.model_validate(json.loads(report.model_dump_json())).suite == "core"


# --- the dataset ---------------------------------------------------------------


def test_the_shipped_dataset_loads() -> None:
    expectations = load_expectations("all")
    assert expectations, "the harness needs scenarios to measure anything"
    assert all(e.objective for e in expectations)


def test_the_dataset_includes_a_negative_case() -> None:
    """Without one, an agent that always finds something would score perfectly."""
    assert any(e.expect_zero_findings for e in load_expectations("all"))


def test_a_confabulating_negative_case_fails_the_build() -> None:
    """No metric can express this: an agent that invents findings scores perfectly on
    coverage and verification while being exactly wrong."""
    report = _report()
    report.scenarios.append(
        ScenarioReport(
            scenario_id="no_contradiction",
            metrics=MetricSet(evidence_coverage=1.0, unsupported_claim_rate=0.0),
            findings=8,
            is_negative_case=True,
            negative_case_passed=False,
        )
    )
    failures = report.build_failures()

    assert failures, "inventing findings on a negative case must fail the build"
    assert "correct answer is none" in failures[0]
    assert "Confabulation" in to_markdown(report)


def test_a_passing_negative_case_does_not_fail_the_build() -> None:
    report = _report()
    report.scenarios.append(
        ScenarioReport(
            scenario_id="no_contradiction",
            metrics=MetricSet(),
            findings=0,
            is_negative_case=True,
            negative_case_passed=True,
        )
    )
    assert report.build_failures() == []


def test_a_positive_scenario_is_never_counted_as_confabulation() -> None:
    report = _report()
    report.scenarios.append(
        ScenarioReport(scenario_id="contradiction", metrics=MetricSet(), findings=5)
    )
    assert report.confabulations == []
