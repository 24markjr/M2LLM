"""One quality figure, with its formula shown, and a trend (Phase 54).

A single number is useful only if a reader can see what went into it. The summary is an unweighted
mean of named components, each a value in 0..1 computed from a committed report, each naming the
report and the scenarios or cases it was measured on:

| Component | From | Formula |
|---|---|---|
| grounding | agent baseline | 1 - unsupported_claim_rate |
| verification | agent baseline | verification_success |
| negatives | agent baseline | share of negative scenarios with no finding |
| claims found | agent baseline | mean share of planted claims found, over positive scenarios |
| open questions | agent baseline | 1 - premature_conclusion_rate (scenarios that test it) |
| challenge | challenge benchmark | catch_rate x (1 - false_alarm_rate) |
| ATT&CK | ATT&CK benchmark | F1 of technique precision and recall |
| injection | trust benchmark | injection detection rate |

Left out on purpose: the Evidence Locker's tamper detection is a hash comparison - right by
construction, and a component fixed at 1.0 would only flatter the mean; its tests guard it.

The trend uses the agent components alone, over every committed agent report, because the
benchmarks have one report each and mixing them in would draw a line through a single point.
"""

from __future__ import annotations

from pathlib import Path

from pydantic import Field

from app.evaluation.attack import AttackReport, attack_dir
from app.evaluation.challenge import ChallengeReport, challenge_dir
from app.evaluation.report import CategorySummary, EvalReport
from app.evaluation.runner import reports_dir
from app.evaluation.trust import TrustReport, trust_dir
from app.schemas.common import JarvisModel

FORMULA = (
    "quality = mean(grounding, verification, negatives, claims found, open questions, challenge, "
    "ATT&CK, injection), each in 0..1 and each from the newest committed report it names"
)
AGENT_FORMULA = (
    "agent quality = mean(grounding, verification, negatives, claims found, open questions), "
    "from one agent report"
)


class QualityComponent(JarvisModel):
    name: str
    value: float
    formula: str
    source: str
    dataset: str


class TrendPoint(JarvisModel):
    generated_at: str
    report: str
    agent_quality: float
    comparable_key: str


class QualitySummary(JarvisModel):
    formula: str = FORMULA
    value: float | None = None
    components: list[QualityComponent] = Field(default_factory=list)
    categories: list[CategorySummary] = Field(default_factory=list)
    agent_formula: str = AGENT_FORMULA
    trend: list[TrendPoint] = Field(default_factory=list)
    missing: list[str] = Field(default_factory=list)


def _newest[T](directory: Path, pattern: str, model: type[T]) -> tuple[T, str] | None:
    paths = sorted(directory.glob(pattern))
    for path in reversed(paths):
        try:
            return model.model_validate_json(path.read_text(encoding="utf-8")), path.name  # type: ignore[attr-defined]
        except (OSError, ValueError):
            continue
    return None


def agent_components(report: EvalReport, name: str) -> list[QualityComponent]:
    agg = report.aggregate
    every = f"{len(report.scenarios)} scenarios, suite {report.suite}"
    out = [
        QualityComponent(
            name="grounding",
            value=1.0 - agg.unsupported_claim_rate,
            formula="1 - unsupported_claim_rate",
            source=name,
            dataset=every,
        ),
        QualityComponent(
            name="verification",
            value=agg.verification_success,
            formula="verification_success",
            source=name,
            dataset=every,
        ),
    ]
    negatives = [s for s in report.scenarios if s.is_negative_case]
    if negatives:
        out.append(
            QualityComponent(
                name="negatives",
                value=sum(s.negative_case_passed for s in negatives) / len(negatives),
                formula="negative scenarios with no finding / negative scenarios",
                source=name,
                dataset=", ".join(s.scenario_id for s in negatives),
            )
        )
    positives = [s for s in report.scenarios if s.is_positive_case]
    if positives:
        out.append(
            QualityComponent(
                name="claims found",
                value=sum(s.expected_claims_found for s in positives) / len(positives),
                formula="mean share of planted claims found",
                source=name,
                dataset=", ".join(s.scenario_id for s in positives),
            )
        )
    rate = report.premature_conclusion_rate
    if rate is not None:
        tested = [s.scenario_id for s in report.scenarios if s.expected_open_hypotheses]
        out.append(
            QualityComponent(
                name="open questions",
                value=1.0 - rate,
                formula="1 - premature_conclusion_rate",
                source=name,
                dataset=", ".join(tested),
            )
        )
    return out


def _mean(components: list[QualityComponent]) -> float | None:
    return sum(c.value for c in components) / len(components) if components else None


def quality_summary() -> QualitySummary:
    summary = QualitySummary()
    components: list[QualityComponent] = []

    agent = _newest(reports_dir(), "*-all.json", EvalReport)
    if agent is None:
        summary.missing.append("no agent baseline (python -m app.cli eval --repeat 3)")
    else:
        report, name = agent
        components += agent_components(report, name)
        summary.categories = report.categories()

    challenge = _newest(challenge_dir() / "reports", "*.json", ChallengeReport)
    if challenge is None:
        summary.missing.append("no challenge report (python -m app.cli eval-challenge)")
    else:
        report_c, name_c = challenge
        components.append(
            QualityComponent(
                name="challenge",
                value=report_c.challenge_catch_rate * (1.0 - report_c.challenge_false_alarm_rate),
                formula="challenge_catch_rate x (1 - challenge_false_alarm_rate)",
                source=name_c,
                dataset=(
                    f"{report_c.false_cases} planted false and {report_c.true_cases} true findings"
                ),
            )
        )

    attack = _newest(attack_dir() / "reports", "*.json", AttackReport)
    if attack is None:
        summary.missing.append("no ATT&CK report (python -m app.cli eval-attack)")
    else:
        report_a, name_a = attack
        p, r = report_a.technique_precision, report_a.technique_recall
        components.append(
            QualityComponent(
                name="ATT&CK",
                value=2 * p * r / (p + r) if p + r else 0.0,
                formula="2 x precision x recall / (precision + recall)",
                source=name_a,
                dataset=", ".join(c.fixture for c in report_a.cases),
            )
        )

    trust = _newest(trust_dir() / "reports", "*.json", TrustReport)
    if trust is None or trust[0].security is None:
        summary.missing.append(
            "no trust report with injection results (python -m app.cli eval-trust)"
        )
    else:
        report_t, name_t = trust
        assert report_t.security is not None
        components.append(
            QualityComponent(
                name="injection",
                value=report_t.security.detection_rate,
                formula="injection detection rate",
                source=name_t,
                dataset=f"{report_t.security.cases} injection cases",
            )
        )

    summary.components = components
    summary.value = _mean(components)

    for path in sorted(reports_dir().glob("*-all.json")):
        try:
            report = EvalReport.model_validate_json(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        value = _mean(agent_components(report, path.name))
        if value is not None:
            summary.trend.append(
                TrendPoint(
                    generated_at=report.generated_at.isoformat(),
                    report=path.name,
                    agent_quality=value,
                    comparable_key=report.comparable_key,
                )
            )
    return summary
