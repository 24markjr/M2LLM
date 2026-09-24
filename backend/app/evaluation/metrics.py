"""The ten metrics.

Every one is a pure function of a scenario's expectation and what a run actually produced.
Nothing here is hard-coded, sampled, or estimated: a number in a report is computed from a
real run or it does not appear.

That constraint is the reason this module has no I/O, no model calls and no configuration.
A scorer that could reach outside its arguments could be influenced by something other than
the run it is scoring, and the whole point of the harness is that it cannot be.

**`unsupported_claim_rate` is the headline.** Every other metric can look healthy while the
system still fails at its purpose: a plan can be valid, tools correctly chosen and tasks
efficiently executed, and the report can still assert things nothing supports. It is the
only metric with a build-failing threshold.
"""

from __future__ import annotations

from pydantic import Field

from app.schemas.common import JarvisModel, UnitFloat
from app.schemas.evidence import EvidenceGap
from app.schemas.finding import Finding
from app.schemas.intent import Intent, Operation
from app.schemas.plan import Plan
from app.schemas.task import TaskStatus
from app.schemas.tool import SelectionMode


class ScenarioExpectation(JarvisModel):
    """Ground truth for one scenario.

    Deliberately partial. Writing full expected output for an investigation is slow and
    subjective; stating the operations that must appear, the edges that must exist and the
    claims that must be found is checkable and hard to fudge.
    """

    scenario_id: str
    objective: str
    documents: list[str] = Field(default_factory=list)

    expected_operations: list[Operation] = Field(default_factory=list)
    min_tasks: int = Field(default=2, ge=0)
    # (dependency, dependent) pairs by task type, since task ids vary between runs.
    expected_edges: list[tuple[str, str]] = Field(default_factory=list)
    expected_tools: dict[str, str] = Field(default_factory=dict)
    # Substrings that must appear in some finding's claim.
    expected_claims: list[str] = Field(default_factory=list)
    # A negative case: the correct answer is that there is nothing here.
    expect_zero_findings: bool = False
    # The smallest task count that could satisfy the objective, for efficiency scoring.
    minimal_tasks: int = Field(default=0, ge=0)


class ScenarioOutcome(JarvisModel):
    """What a run actually produced. Assembled by the runner, scored by this module."""

    scenario_id: str
    intent: Intent | None = None
    plan: Plan | None = None
    findings: list[Finding] = Field(default_factory=list)
    gaps: list[EvidenceGap] = Field(default_factory=list)
    replan_iterations: int = 0
    latency_s: float = 0.0
    llm_calls: int = 0
    repair_attempts: int = 0
    error: str = ""


class MetricSet(JarvisModel):
    """The ten metrics for one scenario or one suite."""

    intent_accuracy: UnitFloat = 0.0
    plan_validity: UnitFloat = 0.0
    dependency_correctness: UnitFloat = 0.0
    tool_selection_accuracy: UnitFloat = 0.0
    evidence_coverage: UnitFloat = 0.0
    verification_success: UnitFloat = 0.0
    replanning_success: UnitFloat = 0.0
    unsupported_claim_rate: UnitFloat = 0.0
    task_efficiency: float = Field(default=0.0, ge=0.0)
    latency_s: float = Field(default=0.0, ge=0.0)

    def as_dict(self) -> dict[str, float]:
        return {name: float(getattr(self, name)) for name in type(self).model_fields}


# --- individual scorers ---------------------------------------------------------


def intent_accuracy(expectation: ScenarioExpectation, outcome: ScenarioOutcome) -> float:
    """F1 over the operation set.

    F1 rather than recall: an intent that requests every operation in the vocabulary would
    score perfect recall while being useless, and precision is what penalises that.
    """
    if not expectation.expected_operations:
        return 1.0
    if outcome.intent is None:
        return 0.0

    expected = set(expectation.expected_operations)
    actual = set(outcome.intent.operations)
    overlap = len(expected & actual)
    if overlap == 0:
        return 0.0

    precision = overlap / len(actual)
    recall = overlap / len(expected)
    return 2 * precision * recall / (precision + recall)


def plan_validity(outcome: ScenarioOutcome) -> float:
    """Whether the plan passed with no repairs and no re-prompts.

    `clean`, not `valid`. A plan rescued by three repairs is executable, but counting it as
    a success would let the planner degrade indefinitely while the metric stayed at 1.0.
    """
    if outcome.plan is None or outcome.plan.validation is None:
        return 0.0
    return 1.0 if outcome.plan.validation.clean else 0.0


def dependency_correctness(expectation: ScenarioExpectation, outcome: ScenarioOutcome) -> float:
    """Edge-level F1 against the expected DAG, compared by task type.

    Task ids vary between runs, so comparing them would measure numbering rather than
    structure. Types are what the ordering is actually about.
    """
    if not expectation.expected_edges:
        return 1.0
    if outcome.plan is None:
        return 0.0

    by_id = {t.task_id: t.task_type.value for t in outcome.plan.tasks}
    actual = {(by_id[a], by_id[b]) for a, b in outcome.plan.edges() if a in by_id and b in by_id}
    expected = {(a, b) for a, b in expectation.expected_edges}

    overlap = len(expected & actual)
    if overlap == 0:
        return 0.0
    precision = overlap / len(actual)
    recall = overlap / len(expected)
    return 2 * precision * recall / (precision + recall)


def tool_selection_accuracy(expectation: ScenarioExpectation, outcome: ScenarioOutcome) -> float:
    """Share of tasks routed to the expected tool, over the types ground truth names."""
    if not expectation.expected_tools or outcome.plan is None:
        return 1.0

    checked = 0
    correct = 0
    for task in outcome.plan.tasks:
        expected_tool = expectation.expected_tools.get(task.task_type.value)
        if expected_tool is None or task.selection is None:
            continue
        checked += 1
        if task.selection.tool_name == expected_tool:
            correct += 1

    return correct / checked if checked else 1.0


def deterministic_routing_share(outcome: ScenarioOutcome) -> float:
    """Share of selections decided without consulting a model.

    Not one of the ten, but reported alongside them: a falling share means the capability
    model has grown too coarse to discriminate, which is a design signal rather than a
    quality one.
    """
    if outcome.plan is None:
        return 0.0
    selections = [t.selection for t in outcome.plan.tasks if t.selection is not None]
    if not selections:
        return 0.0
    deterministic = sum(1 for s in selections if s.mode is SelectionMode.DETERMINISTIC)
    return deterministic / len(selections)


def evidence_coverage(outcome: ScenarioOutcome) -> float:
    """Share of findings with at least one resolved evidence reference."""
    if not outcome.findings:
        # No findings cannot be scored as poor coverage: a correct empty result would
        # otherwise be punished. The negative-case scorer handles that separately.
        return 1.0
    supported = sum(1 for f in outcome.findings if f.has_resolved_evidence)
    return supported / len(outcome.findings)


def verification_success(outcome: ScenarioOutcome) -> float:
    """Share of findings that survived independent verification."""
    verified_or_rejected = [f for f in outcome.findings if f.verification is not None]
    if not verified_or_rejected:
        return 1.0 if not outcome.findings else 0.0
    passed = sum(1 for f in verified_or_rejected if f.is_verified)
    return passed / len(verified_or_rejected)


def replanning_success(outcome: ScenarioOutcome) -> float:
    """Share of detected gaps closed within the iteration ceiling."""
    if not outcome.gaps:
        return 1.0
    closed = sum(1 for g in outcome.gaps if g.resolved)
    return closed / len(outcome.gaps)


def unsupported_claim_rate(outcome: ScenarioOutcome) -> float:
    """Share of findings asserting something no resolved evidence supports.

    The headline metric, and the only one that can fail a build. Every other number can look
    healthy while the report still asserts things nothing supports, which is the precise
    failure this project exists to prevent.
    """
    if not outcome.findings:
        return 0.0
    unsupported = sum(1 for f in outcome.findings if not f.has_resolved_evidence)
    return unsupported / len(outcome.findings)


def task_efficiency(expectation: ScenarioExpectation, outcome: ScenarioOutcome) -> float:
    """Executed tasks divided by the minimal sufficient count. Lower is better; 1.0 is ideal."""
    if outcome.plan is None:
        return 0.0
    minimal = expectation.minimal_tasks or expectation.min_tasks or 1
    executed = sum(
        1 for t in outcome.plan.tasks if t.status in {TaskStatus.COMPLETED, TaskStatus.FAILED}
    ) or len(outcome.plan.tasks)
    return executed / minimal


def negative_case_score(expectation: ScenarioExpectation, outcome: ScenarioOutcome) -> float:
    """For scenarios where the correct answer is that there is nothing to find.

    An agent that always finds something is not investigating, it is confabulating, and no
    positive scenario can detect that.
    """
    if not expectation.expect_zero_findings:
        return 1.0
    return 1.0 if not outcome.findings else 0.0


def claims_found(expectation: ScenarioExpectation, outcome: ScenarioOutcome) -> float:
    """Share of expected claims that appear in some finding.

    Matched on substring rather than equality: two correct phrasings of the same
    contradiction are both correct, and demanding exact wording would measure the model's
    prose style rather than whether it found the thing.
    """
    if not expectation.expected_claims:
        return 1.0
    claims = " ".join(f.claim.lower() for f in outcome.findings)
    found = sum(1 for expected in expectation.expected_claims if expected.lower() in claims)
    return found / len(expectation.expected_claims)


def score_scenario(expectation: ScenarioExpectation, outcome: ScenarioOutcome) -> MetricSet:
    """All ten metrics for one scenario."""
    return MetricSet(
        intent_accuracy=intent_accuracy(expectation, outcome),
        plan_validity=plan_validity(outcome),
        dependency_correctness=dependency_correctness(expectation, outcome),
        tool_selection_accuracy=tool_selection_accuracy(expectation, outcome),
        evidence_coverage=evidence_coverage(outcome),
        verification_success=verification_success(outcome),
        replanning_success=replanning_success(outcome),
        unsupported_claim_rate=unsupported_claim_rate(outcome),
        task_efficiency=task_efficiency(expectation, outcome),
        latency_s=outcome.latency_s,
    )


def aggregate(scores: list[MetricSet]) -> MetricSet:
    """Mean across scenarios.

    An unweighted mean on purpose: weighting by scenario size would let one large scenario
    dominate the suite and hide a regression in everything else.
    """
    if not scores:
        return MetricSet()

    fields = list(MetricSet.model_fields)
    totals = {name: sum(float(getattr(s, name)) for s in scores) / len(scores) for name in fields}
    return MetricSet.model_validate(totals)
