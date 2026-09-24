"""Phase 18 — report synthesis.

The tests that matter enforce the governing rule: facts are injected, prose is generated.
A model cannot introduce a number, a rejected finding cannot be hidden, and the same stored
state always renders the same document.
"""

from __future__ import annotations

import json

import pytest

from app.intelligence.synthesis.engine import ReportNarrative, SynthesisEngine
from app.intelligence.synthesis.renderers import to_dict, to_markdown, to_text
from app.llm.echo import EchoProvider
from app.schemas.common import SourceLocator, new_run_id
from app.schemas.evidence import EvidenceGap, EvidenceRef, GapType, ResolutionStatus
from app.schemas.execution import Observation, TerminationReason
from app.schemas.finding import Confidence, Finding, FindingClassification
from app.schemas.objective import AttachedDocument, Objective, ObjectiveScope
from app.schemas.result import ExecutionSummary, SectionKind
from app.schemas.verification import (
    IssueType,
    VerificationIssue,
    VerificationResult,
    VerificationStatus,
)


def _ref(doc: str, row: int, *, resolved: bool = True) -> EvidenceRef:
    return EvidenceRef(
        locator=SourceLocator(document_id=doc, document_name=doc, row=row),
        resolution=ResolutionStatus.RESOLVED if resolved else ResolutionStatus.UNRESOLVED,
        resolution_note="" if resolved else "no task produced this locator",
    )


def _finding(
    fid: str,
    claim: str,
    *,
    status: VerificationStatus | None = VerificationStatus.SUPPORTED,
    resolved: bool = True,
) -> Finding:
    refs = [_ref("aurora_project_report.txt", 10, resolved=resolved)]
    classification = FindingClassification.FACT if resolved else FindingClassification.UNKNOWN
    verification = None
    if status is not None:
        issues = (
            []
            if status is VerificationStatus.SUPPORTED
            else [
                VerificationIssue(
                    issue_type=IssueType.NO_EVIDENCE, description="nothing establishes this"
                )
            ]
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


def _objective() -> Objective:
    return Objective(
        text="Identify contradictions between the timeline and the financial information.",
        scope=ObjectiveScope(
            documents=[
                AttachedDocument(
                    document_id="aurora_project_report.txt", name="aurora_project_report.txt"
                )
            ]
        ),
    )


def _engine(narrative: str | None = None) -> SynthesisEngine:
    responses = [
        narrative
        or json.dumps(
            {
                "executive_summary": "The investigation established one finding.",
                "reasoning": "The findings are independent.",
            }
        )
    ]
    return SynthesisEngine(EchoProvider(responses={"synthesis": responses}))


async def _report(
    *,
    findings: list[Finding] | None = None,
    gaps: list[EvidenceGap] | None = None,
    observations: list[Observation] | None = None,
    execution: ExecutionSummary | None = None,
    termination: TerminationReason | None = None,
    engine: SynthesisEngine | None = None,
):
    return await (engine or _engine()).synthesize(
        run_id=new_run_id(),
        objective=_objective(),
        findings=findings if findings is not None else [_finding("F-001", "A verified claim.")],
        gaps=gaps or [],
        observations=observations or [],
        execution=execution or ExecutionSummary(tasks_planned=5, tasks_completed=5),
        termination=termination,
    )


# --- structure -----------------------------------------------------------------


async def test_the_report_has_all_eleven_sections() -> None:
    report = await _report()
    assert len(report.sections) == 11
    assert {s.kind for s in report.sections} == set(SectionKind)


async def test_rejected_findings_get_their_own_section() -> None:
    """A report showing only what survived is a highlight reel, not an audit."""
    rejected = _finding("F-002", "A refuted claim.", status=VerificationStatus.CONTRADICTED)
    report = await _report(findings=[_finding("F-001", "Verified."), rejected])

    assert [f.finding_id for f in report.rejected_findings] == ["F-002"]
    section = report.section(SectionKind.REJECTED_FINDINGS)
    assert section is not None
    assert any("F-002" in item for item in section.items)


async def test_findings_are_sorted_into_verified_uncertain_and_rejected() -> None:
    report = await _report(
        findings=[
            _finding("F-001", "Verified."),
            _finding("F-002", "Unsupported.", status=VerificationStatus.UNSUPPORTED),
            _finding("F-003", "Refuted.", status=VerificationStatus.CONTRADICTED),
        ]
    )
    assert [f.finding_id for f in report.verified_findings] == ["F-001"]
    assert [f.finding_id for f in report.uncertain_findings] == ["F-002"]
    assert [f.finding_id for f in report.rejected_findings] == ["F-003"]


# --- facts are injected, not generated -----------------------------------------


async def test_a_model_inventing_a_number_cannot_put_it_in_a_finding() -> None:
    """The narrative is prose only. Every figure is placed from settled state."""
    engine = _engine(
        json.dumps(
            {
                "executive_summary": "Spending reached 999,999 across 42 documents.",
                "reasoning": "There were 17 contradictions.",
            }
        )
    )
    report = await _report(engine=engine)

    section = report.section(SectionKind.VERIFIED_FINDINGS)
    assert section is not None
    assert not any("999,999" in item for item in section.items)
    assert not any("17" in item for item in section.items)


async def test_confidence_comes_from_the_finding_not_the_prose() -> None:
    finding = _finding("F-001", "A claim.")
    report = await _report(findings=[finding])

    section = report.section(SectionKind.VERIFIED_FINDINGS)
    assert section is not None
    assert f"{finding.confidence.value:.2f}" in section.items[0]


async def test_overall_confidence_averages_only_verified_findings() -> None:
    """Averaging in unsupported claims would distort what was actually established."""
    report = await _report(
        findings=[
            _finding("F-001", "Verified."),
            _finding("F-002", "Unsupported.", status=VerificationStatus.UNSUPPORTED),
        ]
    )
    assert report.overall_confidence == pytest.approx(report.verified_findings[0].confidence.value)


async def test_a_report_with_nothing_verified_has_zero_overall_confidence() -> None:
    report = await _report(
        findings=[_finding("F-001", "Unsupported.", status=VerificationStatus.UNSUPPORTED)]
    )
    assert report.overall_confidence == 0.0


# --- limitations are derived from run facts ------------------------------------


async def test_skipped_and_failed_tasks_become_limitations() -> None:
    report = await _report(
        execution=ExecutionSummary(
            tasks_planned=10, tasks_completed=7, tasks_failed=1, tasks_skipped=2
        )
    )
    text = " ".join(entry.description for entry in report.limitations)
    assert "could not be executed" in text
    assert "failed" in text


async def test_an_unresolved_gap_becomes_a_limitation_naming_what_is_missing() -> None:
    gap = EvidenceGap(
        gap_id="G-001",
        finding_id="F-001",
        gap_type=GapType.MISSING_BASELINE,
        missing="the approved baseline completion date",
        suggested_query="approved baseline",
    )
    report = await _report(gaps=[gap])

    assert any(
        "approved baseline completion date" in entry.description for entry in report.limitations
    )


async def test_compacted_observations_are_disclosed() -> None:
    report = await _report(
        observations=[
            Observation(task_id="task_001", task_type="extract", content="x", compacted=True)
        ]
    )
    assert any("summarised" in entry.description for entry in report.limitations)


async def test_hitting_the_iteration_ceiling_is_disclosed() -> None:
    report = await _report(termination=TerminationReason.MAX_ITERATIONS)
    assert any("iteration ceiling" in entry.description for entry in report.limitations)


async def test_unsupported_claims_are_disclosed_as_a_limitation() -> None:
    report = await _report(
        findings=[
            _finding("F-001", "No source.", status=VerificationStatus.UNSUPPORTED, resolved=False)
        ]
    )
    assert any(
        "could not be tied to any source" in entry.description for entry in report.limitations
    )


async def test_a_clean_run_records_no_limitations() -> None:
    report = await _report()
    assert report.limitations == []


# --- resilience ----------------------------------------------------------------


async def test_a_narrative_failure_still_produces_a_complete_report() -> None:
    """Every finding, number and citation is placed by the engine regardless."""
    engine = SynthesisEngine(EchoProvider(responses={"synthesis": ["not json", "no", "nor"]}))
    report = await _report(engine=engine)

    assert len(report.sections) == 11
    summary = report.section(SectionKind.EXECUTIVE_SUMMARY)
    assert summary is not None and summary.narrative, "a fallback summary is written"


async def test_the_report_refuses_to_present_unsupported_claims_as_verified() -> None:
    """The last check before a human reads it."""
    from pydantic import ValidationError

    from app.schemas.result import FinalReport

    unsupported = _finding("F-001", "Nothing supports this.", resolved=False)
    with pytest.raises(ValidationError, match="without resolved evidence"):
        FinalReport(run_id=new_run_id(), objective="x", verified_findings=[unsupported])


# --- rendering -----------------------------------------------------------------


async def test_markdown_renders_every_section_and_the_limitations() -> None:
    report = await _report(
        execution=ExecutionSummary(tasks_planned=5, tasks_completed=4, tasks_skipped=1)
    )
    markdown = to_markdown(report)

    for heading in ("Executive Summary", "Verified Findings", "Rejected Findings", "Limitations"):
        assert f"## {heading}" in markdown
    assert "could not be executed" in markdown


async def test_rendering_is_deterministic() -> None:
    """The same stored run must always produce the same document."""
    report = await _report()
    assert to_markdown(report) == to_markdown(report)
    assert to_text(report) == to_text(report)


async def test_text_rendering_is_ascii_only() -> None:
    """The Windows console is cp1252 by default (BUG-001)."""
    report = await _report()
    assert to_text(report).isascii()


async def test_the_json_shape_round_trips() -> None:
    from app.schemas.result import FinalReport

    report = await _report()
    assert FinalReport.model_validate(to_dict(report)).run_id == report.run_id


def test_the_narrative_model_carries_only_prose() -> None:
    """There is nowhere for a generated number to enter the report."""
    assert set(ReportNarrative.model_fields) == {"executive_summary", "reasoning"}


async def test_model_prose_is_rendered_printable_on_any_console() -> None:
    """The narrative is the one model-written part of the report, so it is the one part
    that arrives with smart quotes. A report that renders as "Aurora?s" undermines the
    document it is trying to make authoritative (BUG-001)."""
    engine = _engine(
        json.dumps(
            {
                "executive_summary": "Aurora’s baseline — 30 April — was missed.",
                "reasoning": "The “baseline” and the milestone disagree…",
            }
        )
    )
    report = await _report(engine=engine)

    text = to_text(report)
    assert text.isascii()
    assert "Aurora's baseline - 30 April - was missed." in text
    assert to_markdown(report).isascii()
