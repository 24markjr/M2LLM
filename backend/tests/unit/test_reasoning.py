"""Phase 13 — the reasoning engine and the evidence binder.

The binder tests carry the weight. They prove the system does not take the model's citations
at face value, which is the difference between "evidence-backed" and "the model wrote
something in an evidence-shaped field".
"""

from __future__ import annotations

import json

import pytest

from app.core.events import EventBus, MemoryEventSink, RunEventEmitter
from app.intelligence.reasoning.engine import (
    EvidenceBinder,
    ReasoningEngine,
    parse_locator,
    source_agreement,
)
from app.llm.echo import EchoProvider
from app.schemas.common import new_run_id
from app.schemas.event import EventType
from app.schemas.execution import Observation
from app.schemas.finding import FindingClassification
from app.schemas.objective import Objective

OBSERVATIONS = [
    Observation(
        task_id="task_001",
        task_type="extract_timeline",
        content="4 date(s)",
        structured={
            "extractions": [
                {
                    "document_id": "project_report.txt",
                    "line": 10,
                    "value": "2026-04-30",
                    "kind": "date",
                }
            ]
        },
        sources=["project_report.txt:r10"],
    ),
    Observation(
        task_id="task_002",
        task_type="extract_timeline",
        content="4 date(s)",
        structured={
            "extractions": [
                {
                    "document_id": "milestone_report.txt",
                    "line": 7,
                    "value": "2026-05-14",
                    "kind": "date",
                }
            ]
        },
        sources=["milestone_report.txt:r7"],
    ),
]


def _findings_json(*findings: tuple[str, list[str]]) -> str:
    return json.dumps(
        {
            "findings": [
                {"claim": claim, "citations": citations, "classification": "FACT"}
                for claim, citations in findings
            ]
        }
    )


def _engine(*responses: str) -> ReasoningEngine:
    return ReasoningEngine(EchoProvider(responses={"reasoning": list(responses)}))


# --- locator parsing -----------------------------------------------------------


@pytest.mark.parametrize(
    ("raw", "document", "row"),
    [
        ("project_report.txt:r10", "project_report.txt", 10),
        ("budget.csv:r2", "budget.csv", 2),
        ("  report.txt:r1  ", "report.txt", 1),
    ],
)
def test_well_formed_locators_parse(raw: str, document: str, row: int) -> None:
    locator = parse_locator(raw)
    assert locator is not None
    assert locator.document_id == document
    assert locator.row == row


def test_page_locators_parse() -> None:
    locator = parse_locator("report.pdf:p12")
    assert locator is not None and locator.page == 12


@pytest.mark.parametrize("raw", ["not a locator", "", "report.txt", "report.txt:", ":r10"])
def test_malformed_citations_do_not_parse(raw: str) -> None:
    """A model inventing a citation usually invents the format too."""
    assert parse_locator(raw) is None


# --- the binder ----------------------------------------------------------------


def test_a_citation_matching_a_real_locator_resolves() -> None:
    refs, evidence = EvidenceBinder(OBSERVATIONS).bind(["project_report.txt:r10"])
    assert len(refs) == 1
    assert refs[0].is_resolved
    assert evidence[0].content.startswith("project_report.txt:r10")


def test_an_invented_citation_is_kept_and_marked_unresolved() -> None:
    """Dropping it would make the claim look better supported than it is."""
    refs, evidence = EvidenceBinder(OBSERVATIONS).bind(["imaginary.txt:r99"])
    assert len(refs) == 1, "the citation is kept, not discarded"
    assert not refs[0].is_resolved
    assert "no task produced this locator" in refs[0].resolution_note
    assert evidence == []


def test_a_malformed_citation_is_marked_unresolved() -> None:
    refs, _ = EvidenceBinder(OBSERVATIONS).bind(["see the report"])
    assert not refs[0].is_resolved
    assert "not a well-formed locator" in refs[0].resolution_note


def test_binding_mixes_resolved_and_unresolved() -> None:
    refs, evidence = EvidenceBinder(OBSERVATIONS).bind(["project_report.txt:r10", "ghost.txt:r1"])
    assert [r.is_resolved for r in refs] == [True, False]
    assert len(evidence) == 1


def test_resolved_evidence_names_the_task_that_produced_it() -> None:
    _, evidence = EvidenceBinder(OBSERVATIONS).bind(["milestone_report.txt:r7"])
    assert evidence[0].retrieved_by_task_id == "task_002"


# --- source agreement ----------------------------------------------------------


def test_two_documents_agreeing_scores_higher_than_one() -> None:
    binder = EvidenceBinder(OBSERVATIONS)
    single, _ = binder.bind(["project_report.txt:r10"])
    both, _ = EvidenceBinder(OBSERVATIONS).bind(
        ["project_report.txt:r10", "milestone_report.txt:r7"]
    )
    assert source_agreement(both) > source_agreement(single)


def test_no_resolved_evidence_scores_zero_agreement() -> None:
    refs, _ = EvidenceBinder(OBSERVATIONS).bind(["ghost.txt:r1"])
    assert source_agreement(refs) == 0.0


# --- the engine ----------------------------------------------------------------


async def test_a_well_cited_claim_becomes_a_finding_with_evidence() -> None:
    engine = _engine(
        _findings_json(
            (
                "The completion date in the programme report conflicts with the milestone report.",
                ["project_report.txt:r10", "milestone_report.txt:r7"],
            )
        )
    )
    findings = await engine.derive_findings(Objective(text="Find contradictions."), OBSERVATIONS)

    assert len(findings) == 1
    finding = findings[0]
    assert finding.resolved_evidence_count == 2
    assert finding.confidence.value > 0.5
    assert finding.classification is FindingClassification.INFERENCE


async def test_a_claim_the_model_calls_FACT_is_downgraded_when_a_citation_fails() -> None:
    """The model's classification is advisory. The stricter computed answer wins."""
    engine = _engine(
        _findings_json(
            ("The project overran by two weeks.", ["project_report.txt:r10", "ghost.txt:r1"])
        )
    )
    findings = await engine.derive_findings(Objective(text="Check."), OBSERVATIONS)

    assert findings[0].classification is FindingClassification.HYPOTHESIS
    assert findings[0].confidence.value <= 0.4, "capped by the hypothesis ceiling"


async def test_a_claim_with_no_resolvable_citation_is_unknown_with_zero_confidence() -> None:
    engine = _engine(_findings_json(("Everything is fine.", ["invented.txt:r1"])))
    findings = await engine.derive_findings(Objective(text="Check."), OBSERVATIONS)

    assert findings[0].classification is FindingClassification.UNKNOWN
    assert findings[0].confidence.value == 0.0
    assert not findings[0].has_resolved_evidence


async def test_a_claim_with_no_citations_at_all_is_unknown() -> None:
    engine = _engine(_findings_json(("Trust me.", [])))
    findings = await engine.derive_findings(Objective(text="Check."), OBSERVATIONS)

    assert findings[0].classification is FindingClassification.UNKNOWN
    assert findings[0].confidence.value == 0.0


async def test_confidence_is_never_taken_from_the_model() -> None:
    """The model is not asked for a number, and there is nowhere to put one if it offered."""
    raw = json.dumps(
        {
            "findings": [
                {
                    "claim": "Dates conflict.",
                    "citations": ["project_report.txt:r10"],
                    "classification": "FACT",
                }
            ]
        }
    )
    findings = await _engine(raw).derive_findings(Objective(text="Check."), OBSERVATIONS)

    confidence = findings[0].confidence
    assert confidence.resolution_rate == 1.0
    assert confidence.value == pytest.approx(
        confidence.resolution_rate * confidence.evidence_strength * confidence.source_agreement,
        rel=1e-6,
    )


async def test_empty_claims_are_skipped() -> None:
    findings = await _engine(_findings_json(("", ["project_report.txt:r10"]))).derive_findings(
        Objective(text="Check."), OBSERVATIONS
    )
    assert findings == []


async def test_no_observations_yields_no_findings_and_no_model_call() -> None:
    provider = EchoProvider()
    findings = await ReasoningEngine(provider).derive_findings(Objective(text="Check."), [])
    assert findings == []
    assert provider.calls == []


async def test_a_model_failure_yields_no_findings_rather_than_invented_ones() -> None:
    """No findings is an honest outcome. Inventing one to fill the gap is not."""
    engine = _engine("not json", "still not json", "nor this")
    findings = await engine.derive_findings(Objective(text="Check."), OBSERVATIONS)
    assert findings == []


async def test_observations_are_rendered_with_their_locators() -> None:
    """The model must be able to copy citations verbatim, or it will invent them."""
    provider = EchoProvider(responses={"reasoning": [_findings_json(("x", []))]})
    await ReasoningEngine(provider).derive_findings(Objective(text="Check."), OBSERVATIONS)

    prompt = provider.calls[0].prompt
    assert "project_report.txt:r10" in prompt
    assert "2026-04-30" in prompt, "the extracted value travels with the locator"


async def test_findings_are_recorded_on_the_timeline() -> None:
    memory = MemoryEventSink()
    emitter = RunEventEmitter(EventBus([memory]), new_run_id())
    engine = _engine(_findings_json(("Dates conflict.", ["project_report.txt:r10"])))

    await engine.derive_findings(Objective(text="Check."), OBSERVATIONS, emit=emitter)

    assert memory.of_type(EventType.REASONING_STARTED)
    created = memory.of_type(EventType.FINDING_CREATED)
    assert len(created) == 1
    assert created[0].payload["classification"]
    assert created[0].payload["resolved_evidence"] == 1
