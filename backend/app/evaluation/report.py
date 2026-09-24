"""Evaluation reports, and the regression check that gives them teeth.

A report is only meaningful against a stamp. Two numbers produced by different models, or
different prompt versions, are not comparable, and quietly comparing them would turn a model
swap into an apparent regression — or hide a real one behind an upgrade. Every report
records the model, the prompt versions and a config hash, and the regression check refuses
to compare across a change in any of them.

Reports are generated files. Nothing here is written by hand, and a number that did not come
out of a run cannot appear in one.
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime
from pathlib import Path

from pydantic import Field

from app.evaluation.metrics import MetricSet
from app.schemas.common import JarvisModel, utcnow

# Direction each metric should move. Everything else is higher-is-better.
LOWER_IS_BETTER = frozenset({"unsupported_claim_rate", "task_efficiency", "latency_s"})

# The one metric that can fail a build outright.
FAIL_BUILD_ABOVE = {"unsupported_claim_rate": 0.15}


class ScenarioReport(JarvisModel):
    scenario_id: str
    metrics: MetricSet
    findings: int = 0
    gaps: int = 0
    gaps_closed: int = 0
    error: str = ""

    # Negative cases: the correct answer is that there is nothing to find. Reported
    # separately because none of the ten metrics can express it - an agent that invents
    # findings scores perfectly on coverage and verification while being exactly wrong.
    is_negative_case: bool = False
    negative_case_passed: bool = True

    @property
    def ok(self) -> bool:
        return not self.error

    @property
    def confabulated(self) -> bool:
        return self.is_negative_case and not self.negative_case_passed


class EvalReport(JarvisModel):
    """One evaluation run over one suite."""

    suite: str
    generated_at: datetime = Field(default_factory=utcnow)

    # The stamp. Without it, two reports are not comparable.
    model: str = ""
    prompt_versions: dict[str, int] = Field(default_factory=dict)
    config_hash: str = ""

    scenarios: list[ScenarioReport] = Field(default_factory=list)
    aggregate: MetricSet = Field(default_factory=MetricSet)

    @property
    def comparable_key(self) -> str:
        """Two reports compare only when this matches."""
        versions = ",".join(f"{k}={v}" for k, v in sorted(self.prompt_versions.items()))
        return f"{self.model}|{versions}|{self.config_hash}"

    @property
    def failed_scenarios(self) -> list[ScenarioReport]:
        return [s for s in self.scenarios if not s.ok]

    @property
    def confabulations(self) -> list[ScenarioReport]:
        """Negative cases where the agent found something that is not there."""
        return [s for s in self.scenarios if s.confabulated]

    def build_failures(self) -> list[str]:
        """Thresholds that fail the build outright, not merely regress."""
        failures: list[str] = []
        for scenario in self.confabulations:
            failures.append(
                f"{scenario.scenario_id} is a negative case but produced "
                f"{scenario.findings} finding(s); the correct answer is none"
            )
        for metric, ceiling in FAIL_BUILD_ABOVE.items():
            value = float(getattr(self.aggregate, metric))
            if value > ceiling:
                failures.append(f"{metric} is {value:.3f}, above the maximum of {ceiling:.2f}")
        return failures


class MetricDelta(JarvisModel):
    metric: str
    baseline: float
    current: float
    tolerance: float

    @property
    def change(self) -> float:
        return self.current - self.baseline

    @property
    def regressed(self) -> bool:
        if self.metric in LOWER_IS_BETTER:
            return self.change > self.tolerance
        return -self.change > self.tolerance

    @property
    def improved_beyond_tolerance(self) -> bool:
        """An unexplained jump usually means the measurement broke, not the agent improved."""
        if self.metric in LOWER_IS_BETTER:
            return -self.change > self.tolerance
        return self.change > self.tolerance


class RegressionResult(JarvisModel):
    comparable: bool = True
    reason: str = ""
    deltas: list[MetricDelta] = Field(default_factory=list)

    @property
    def regressions(self) -> list[MetricDelta]:
        return [d for d in self.deltas if d.regressed]

    @property
    def unexplained_improvements(self) -> list[MetricDelta]:
        return [d for d in self.deltas if d.improved_beyond_tolerance]

    @property
    def passed(self) -> bool:
        return self.comparable and not self.regressions


def config_hash(settings_snapshot: dict[str, object]) -> str:
    """A stable digest of the settings a run depended on."""
    payload = json.dumps(settings_snapshot, sort_keys=True, default=str)
    return "sha256:" + hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]


def compare(
    baseline: EvalReport, current: EvalReport, tolerances: dict[str, float]
) -> RegressionResult:
    """Compare two reports, refusing to compare incomparable ones.

    A model or prompt change makes the numbers describe different systems. Reporting that
    as a regression would be wrong, and reporting it as a pass would be worse.
    """
    if baseline.comparable_key != current.comparable_key:
        return RegressionResult(
            comparable=False,
            reason=(
                "the baseline was produced with a different model, prompt version or "
                "configuration; the numbers describe different systems"
            ),
        )

    deltas = [
        MetricDelta(
            metric=name,
            baseline=float(getattr(baseline.aggregate, name)),
            current=float(getattr(current.aggregate, name)),
            tolerance=tolerances.get(name, 0.05),
        )
        for name in MetricSet.model_fields
    ]
    return RegressionResult(deltas=deltas)


# --- rendering ------------------------------------------------------------------


def to_markdown(report: EvalReport) -> str:
    """ASCII-only rendering (BUG-001)."""
    lines = [
        "# JARVIS Agent Evaluation",
        "",
        f"**Suite:** {report.suite}  ",
        f"**Model:** {report.model}  ",
        f"**Generated:** {report.generated_at:%Y-%m-%d %H:%M UTC}  ",
        f"**Config:** `{report.config_hash}`  ",
        f"**Prompts:** {report.prompt_versions or '(none loaded)'}",
        "",
        "All figures below are computed from real runs. No value is hard-coded.",
        "",
        "## Aggregate",
        "",
        "| Metric | Value | Direction |",
        "|---|---|---|",
    ]

    for name, value in report.aggregate.as_dict().items():
        direction = "lower is better" if name in LOWER_IS_BETTER else "higher is better"
        formatted = f"{value:.2f}" if name in {"latency_s", "task_efficiency"} else f"{value:.3f}"
        lines.append(f"| {name} | {formatted} | {direction} |")

    lines += [
        "",
        "## Per scenario",
        "",
        "| Scenario | Coverage | Unsupported | Verified | Gaps closed |",
        "|---|---|---|---|---|",
    ]
    for scenario in report.scenarios:
        metrics = scenario.metrics
        lines.append(
            f"| {scenario.scenario_id} "
            f"| {metrics.evidence_coverage:.2f} "
            f"| {metrics.unsupported_claim_rate:.2f} "
            f"| {metrics.verification_success:.2f} "
            f"| {scenario.gaps_closed}/{scenario.gaps} |"
        )

    failures = report.build_failures()
    lines += ["", "## Thresholds", ""]
    if failures:
        lines.append("**FAILED**")
        lines += [f"- {failure}" for failure in failures]
    else:
        lines.append("All build-failing thresholds passed.")

    if report.confabulations:
        lines += ["", "## Confabulation", ""]
        lines.append(
            "These scenarios have no answer to find. Producing findings on them means the "
            "agent invented something, which no positive scenario can detect."
        )
        lines += [
            f"- {s.scenario_id}: {s.findings} finding(s) where none should exist"
            for s in report.confabulations
        ]

    if report.failed_scenarios:
        lines += ["", "## Scenarios that did not complete", ""]
        lines += [f"- {s.scenario_id}: {s.error}" for s in report.failed_scenarios]

    lines.append("")
    return "\n".join(lines)


def write_report(report: EvalReport, directory: Path) -> tuple[Path, Path]:
    """Write the JSON and Markdown forms. Returns both paths."""
    directory.mkdir(parents=True, exist_ok=True)
    stamp = report.generated_at.strftime("%Y%m%dT%H%M%S")
    slug = report.model.replace(":", "-") or "unknown"

    json_path = directory / f"{stamp}-{slug}-{report.suite}.json"
    md_path = directory / f"{stamp}-{slug}-{report.suite}.md"

    json_path.write_text(json.dumps(report.model_dump(mode="json"), indent=2), encoding="utf-8")
    md_path.write_text(to_markdown(report), encoding="utf-8")
    return json_path, md_path


def load_latest(directory: Path, suite: str) -> EvalReport | None:
    """The most recent committed report for a suite, or None if there is no baseline."""
    if not directory.exists():
        return None
    candidates = sorted(directory.glob(f"*-{suite}.json"))
    if not candidates:
        return None
    return EvalReport.model_validate_json(candidates[-1].read_text(encoding="utf-8"))
