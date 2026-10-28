"""Phase 54: evaluation v2 - categories, and one quality figure with its formula shown."""

from __future__ import annotations

import pytest
from httpx import ASGITransport, AsyncClient

from app.api.app import create_app
from app.evaluation.metrics import MetricSet
from app.evaluation.quality import agent_components, quality_summary
from app.evaluation.report import EvalReport, ScenarioReport
from app.evaluation.runner import load_expectations


def _scenario(sid: str, category: str, **kwargs: object) -> ScenarioReport:
    return ScenarioReport.model_validate(
        {"scenario_id": sid, "metrics": MetricSet().model_dump(), "category": category, **kwargs}
    )


def test_every_scenario_has_a_category() -> None:
    expectations = load_expectations("all")
    assert len(expectations) == 28  # five Kestrel scenarios since B2, three Indian-language (v4 6)
    assert all(e.category != "uncategorised" for e in expectations)
    assert {e.category for e in expectations} >= {
        "temporal_contradiction",
        "negative",
        "noisy_ocr",
        "conflicting_authority",
        "hypotheses",
        "cyber",
        "injection",
    }


def test_categories_name_their_scenarios_and_their_own_rates() -> None:
    report = EvalReport(
        suite="all",
        scenarios=[
            _scenario("a", "negative", is_negative_case=True, negative_case_passed=True),
            _scenario("b", "negative", is_negative_case=True, negative_case_passed=False),
            _scenario("c", "cyber", is_positive_case=True, expected_claims_found=0.5),
        ],
    )
    by_name = {c.category: c for c in report.categories()}
    assert by_name["negative"].scenarios == ["a", "b"]
    assert by_name["negative"].negative_passed == 0.5
    assert by_name["negative"].claims_found is None, "no positive scenario: no rate, not zero"
    assert by_name["cyber"].claims_found == 0.5


def test_a_report_written_before_categories_still_reads() -> None:
    report = EvalReport.model_validate(
        {"suite": "all", "scenarios": [{"scenario_id": "x", "metrics": MetricSet().model_dump()}]}
    )
    assert [c.category for c in report.categories()] == ["uncategorised"]


def test_agent_components_are_each_named_with_their_formula_and_dataset() -> None:
    report = EvalReport(
        suite="all",
        aggregate=MetricSet(unsupported_claim_rate=0.1, verification_success=0.9),
        scenarios=[
            _scenario("neg", "negative", is_negative_case=True, negative_case_passed=True),
            _scenario("pos", "x", is_positive_case=True, expected_claims_found=0.6),
        ],
    )
    components = {c.name: c for c in agent_components(report, "r.json")}
    assert components["grounding"].value == pytest.approx(0.9)
    assert components["grounding"].formula == "1 - unsupported_claim_rate"
    assert components["negatives"].dataset == "neg"
    assert components["claims found"].value == pytest.approx(0.6)
    assert "open questions" not in components, "no scenario tests it, so it is not counted"


def test_the_summary_is_the_mean_of_what_it_lists() -> None:
    summary = quality_summary()
    assert summary.components, "the committed reports give components"
    assert summary.value == pytest.approx(
        sum(c.value for c in summary.components) / len(summary.components)
    )
    names = {c.name for c in summary.components}
    assert {"grounding", "challenge", "ATT&CK", "injection"} <= names
    assert all(c.source and c.dataset and c.formula for c in summary.components)


async def test_the_endpoint_serves_it() -> None:
    async with AsyncClient(transport=ASGITransport(app=create_app()), base_url="http://test") as c:
        body = (await c.get("/api/v1/evaluation/quality")).json()
    assert body["formula"].startswith("quality = mean(")
    assert body["components"] and body["trend"]
