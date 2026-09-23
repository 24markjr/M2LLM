"""Phase 14 — evidence gap detection.

The tests that matter check *specificity*. A gap saying "more evidence needed" has failed at
its job; a gap must name the element that is missing, because that name is what becomes a
retrieval query.
"""

from __future__ import annotations

import pytest

from app.core.events import EventBus, MemoryEventSink, RunEventEmitter
from app.intelligence.evidence_gap.detector import (
    EvidenceGapDetector,
    check_support,
    decompose,
    emit_gaps,
    mentions_baseline,
    propose_task,
)
from app.schemas.common import SourceLocator, new_run_id
from app.schemas.event import EventType
from app.schemas.evidence import Evidence, EvidenceRef, GapType, ResolutionStatus
from app.schemas.finding import Finding
from app.schemas.task import TaskType


def _locator(doc: str, row: int) -> SourceLocator:
    return SourceLocator(document_id=doc, document_name=doc, row=row)


def _evidence(doc: str, row: int, content: str) -> Evidence:
    return Evidence(evidence_id=f"E-{row:03d}", locator=_locator(doc, row), content=content)


def _resolved(doc: str, row: int) -> EvidenceRef:
    return EvidenceRef(locator=_locator(doc, row), resolution=ResolutionStatus.RESOLVED)


def _unresolved(doc: str, row: int) -> EvidenceRef:
    return EvidenceRef(
        locator=_locator(doc, row),
        resolution=ResolutionStatus.UNRESOLVED,
        resolution_note="no task produced this locator",
    )


def _finding(claim: str, refs: list[EvidenceRef]) -> Finding:
    return Finding(finding_id="F-001", claim=claim, evidence=refs)


# --- decomposition -------------------------------------------------------------


def test_a_claim_is_split_into_checkable_elements() -> None:
    """Checking a claim whole gives supported or not. Checking elements says which part."""
    elements = decompose("The Helix migration completed on 2026-05-14, overspending by 70,000.")
    kinds = {e.kind for e in elements}

    assert "date" in kinds
    assert "quantity" in kinds
    assert "relation" in kinds
    assert any(e.text == "2026-05-14" for e in elements)
    assert any(e.text == "70,000" for e in elements)


def test_sentence_opening_words_are_not_treated_as_entities() -> None:
    elements = decompose("The project slipped.")
    assert not any(e.kind == "entity" and e.text == "The" for e in elements)


def test_every_claim_yields_at_least_the_relation_element() -> None:
    """The claim as a whole can be unsupported even when every part is present."""
    elements = decompose("things are bad")
    assert [e.kind for e in elements] == ["relation"]


def test_decomposition_does_not_duplicate_elements() -> None:
    elements = decompose("2026-05-14 and again 2026-05-14")
    assert sum(1 for e in elements if e.text == "2026-05-14") == 1


# --- element-level support -----------------------------------------------------


def test_an_element_the_evidence_contains_is_supported() -> None:
    elements = check_support(
        decompose("Completion was 2026-05-14."),
        [_evidence("milestone.txt", 7, "M4 go-live closed 2026-05-14.")],
    )
    date = next(e for e in elements if e.kind == "date")
    assert date.supported


def test_an_element_the_evidence_lacks_is_unsupported() -> None:
    elements = check_support(
        decompose("Completion was 2026-05-14."),
        [_evidence("report.txt", 3, "Target completion is 2026-04-30.")],
    )
    date = next(e for e in elements if e.kind == "date")
    assert not date.supported


def test_a_relation_needs_two_distinct_sources() -> None:
    """One source stating something is not the same as corroboration."""
    single = check_support(
        decompose("The dates conflict."), [_evidence("a.txt", 1, "date 2026-04-30")]
    )
    both = check_support(
        decompose("The dates conflict."),
        [_evidence("a.txt", 1, "date 2026-04-30"), _evidence("b.txt", 2, "date 2026-05-14")],
    )
    assert not next(e for e in single if e.kind == "relation").supported
    assert next(e for e in both if e.kind == "relation").supported


# --- baseline detection --------------------------------------------------------


@pytest.mark.parametrize(
    "claim",
    [
        "The project slipped against the approved baseline.",
        "Delivery was later than originally planned.",
        "Spend exceeded the authorised figure.",
    ],
)
def test_claims_measured_against_a_baseline_are_recognised(claim: str) -> None:
    assert mentions_baseline(claim)


def test_a_claim_with_no_baseline_language_is_not_flagged() -> None:
    assert not mentions_baseline("Two documents give different dates.")


# --- detection -----------------------------------------------------------------


def test_an_unresolved_citation_produces_a_named_gap() -> None:
    finding = _finding("The project overran.", [_resolved("a.txt", 1), _unresolved("ghost.txt", 9)])
    gaps = EvidenceGapDetector().detect(finding, [_evidence("a.txt", 1, "The project overran.")])

    unresolved = [g for g in gaps if g.gap_type is GapType.UNRESOLVED_CITATION]
    assert len(unresolved) == 1
    assert "ghost.txt:r9" in unresolved[0].missing


def test_a_missing_baseline_is_detected_and_named_specifically() -> None:
    """The headline behaviour: not "unsure", but "the approved baseline"."""
    finding = _finding(
        "The project slipped two weeks against the approved baseline.", [_resolved("a.txt", 1)]
    )
    gaps = EvidenceGapDetector().detect(finding, [_evidence("a.txt", 1, "M4 closed 2026-05-14.")])

    baseline = [g for g in gaps if g.gap_type is GapType.MISSING_BASELINE]
    assert len(baseline) == 1
    assert "baseline" in baseline[0].missing
    assert baseline[0].severity >= 0.8, "a missing baseline undermines the whole claim"


def test_no_baseline_gap_when_the_evidence_establishes_one() -> None:
    finding = _finding("Delivery slipped against the approved plan.", [_resolved("a.txt", 1)])
    gaps = EvidenceGapDetector().detect(
        finding, [_evidence("a.txt", 1, "The approved baseline completion date is 2026-04-30.")]
    )
    assert not [g for g in gaps if g.gap_type is GapType.MISSING_BASELINE]


def test_an_unsupported_element_becomes_its_own_gap() -> None:
    finding = _finding("Spend reached 450,000 by 2026-05-14.", [_resolved("a.txt", 1)])
    gaps = EvidenceGapDetector().detect(finding, [_evidence("a.txt", 1, "Spend reached 450,000.")])

    missing = [g for g in gaps if g.gap_type is GapType.MISSING_SOURCE]
    assert any("2026-05-14" in g.missing for g in missing)


def test_a_finding_with_no_resolved_evidence_gets_a_gap() -> None:
    finding = _finding("Everything is fine.", [_unresolved("ghost.txt", 1)])
    gaps = EvidenceGapDetector().detect(finding, [])
    assert gaps


def test_a_fully_supported_claim_produces_no_element_gaps() -> None:
    finding = _finding(
        "Completion was 2026-05-14.",
        [_resolved("a.txt", 1), _resolved("b.txt", 2)],
    )
    gaps = EvidenceGapDetector().detect(
        finding,
        [
            _evidence("a.txt", 1, "Completion was 2026-05-14."),
            _evidence("b.txt", 2, "Go-live 2026-05-14."),
        ],
    )
    assert not [g for g in gaps if g.gap_type is GapType.MISSING_SOURCE]


def test_every_gap_names_something_specific() -> None:
    """'More evidence needed' is not a gap. A gap names an element."""
    finding = _finding(
        "The Helix project slipped against the approved baseline by 2026-05-14.",
        [_resolved("a.txt", 1), _unresolved("ghost.txt", 2)],
    )
    gaps = EvidenceGapDetector().detect(finding, [_evidence("a.txt", 1, "nothing relevant")])

    assert gaps
    for gap in gaps:
        assert len(gap.missing) > 15, f"gap is not specific: {gap.missing!r}"
        assert gap.suggested_query.strip(), "a gap without a query is not actionable"


def test_detection_is_deterministic() -> None:
    """The model is not asked whether a gap exists, so the answer cannot drift."""
    finding = _finding("Slipped against the approved baseline.", [_resolved("a.txt", 1)])
    evidence = [_evidence("a.txt", 1, "M4 closed late.")]

    first = EvidenceGapDetector().detect(finding.model_copy(deep=True), evidence)
    second = EvidenceGapDetector().detect(finding.model_copy(deep=True), evidence)

    assert [(g.gap_type, g.missing) for g in first] == [(g.gap_type, g.missing) for g in second]


def test_gap_ids_are_unique_within_a_detector() -> None:
    detector = EvidenceGapDetector()
    finding = _finding(
        "Slipped against the approved baseline by 2026-05-14.",
        [_resolved("a.txt", 1), _unresolved("g.txt", 2)],
    )
    gaps = detector.detect(finding, [_evidence("a.txt", 1, "unrelated")])
    assert len({g.gap_id for g in gaps}) == len(gaps)


# --- task proposal: the step that makes a gap actionable -----------------------


def test_a_gap_becomes_a_retrieval_task_carrying_its_query() -> None:
    finding = _finding("Slipped against the approved baseline.", [_resolved("a.txt", 1)])
    gap = next(
        g
        for g in EvidenceGapDetector().detect(finding, [_evidence("a.txt", 1, "closed late")])
        if g.gap_type is GapType.MISSING_BASELINE
    )

    task = propose_task(gap, index=9)

    assert task.task_type is TaskType.RETRIEVE_EVIDENCE
    assert task.inputs["query"] == gap.suggested_query
    assert task.inputs["query"], "the task must carry a concrete query"


def test_a_proposed_task_records_the_gap_that_caused_it() -> None:
    """An inserted task must always be explainable."""
    finding = _finding("Slipped against the approved baseline.", [_resolved("a.txt", 1)])
    gap = EvidenceGapDetector().detect(finding, [_evidence("a.txt", 1, "x")])[0]

    task = propose_task(gap, index=9)
    assert task.created_for_gap_id == gap.gap_id


# --- tracing -------------------------------------------------------------------


async def test_gaps_are_recorded_on_the_timeline() -> None:
    memory = MemoryEventSink()
    emitter = RunEventEmitter(EventBus([memory]), new_run_id())
    finding = _finding("Slipped against the approved baseline.", [_resolved("a.txt", 1)])
    gaps = EvidenceGapDetector().detect(finding, [_evidence("a.txt", 1, "closed late")])

    await emit_gaps(gaps, emitter)

    detected = memory.of_type(EventType.EVIDENCE_GAP_DETECTED)
    assert len(detected) == len(gaps)
    assert detected[0].payload["missing"]
    assert detected[0].payload["query"]
