"""Phase 37: the report's model-written prose, checked sentence by sentence (Member 4's T5).

Synthesis places every fact; the model writes the executive summary and the reasoning paragraph.
These tests hold the check on those two paragraphs to what it promises: grounded sentences pass,
invented ones are named with the value nothing contains, the report is never rewritten, and the
verdict reaches the event stream and both renderings.
"""

from __future__ import annotations

import json

from app.core.events import EventBus, MemoryEventSink, RunEventEmitter
from app.intelligence.synthesis.engine import SynthesisEngine
from app.intelligence.synthesis.grounding import check_narrative, evidence_for
from app.intelligence.synthesis.renderers import to_markdown, to_text
from app.intelligence.trust.answer import evaluate_answer, overall_status
from app.llm.echo import EchoProvider
from app.schemas.common import SourceLocator, new_run_id
from app.schemas.event import EventType
from app.schemas.evidence import EvidenceRef, ResolutionStatus
from app.schemas.finding import Finding
from app.schemas.objective import Objective
from app.schemas.result import ExecutionSummary, SectionKind
from app.schemas.trust import EvidenceText, TrustStatus
from app.schemas.verification import VerificationResult, VerificationStatus

LINE = "Shipment 4821 arrived on 14 September at the Mumbai warehouse, received by Rahul Sharma."
EVIDENCE = [EvidenceText(source="shipment_report_a.txt:r1", content=LINE)]


def _finding(source: str, *, resolved: bool = True) -> Finding:
    document, _, row = source.rpartition(":r")
    return Finding(
        finding_id="F-001",
        claim="Shipment 4821 arrived on 14 September.",
        evidence=[
            EvidenceRef(
                locator=SourceLocator(document_id=document, document_name=document, row=int(row)),
                resolution=ResolutionStatus.RESOLVED if resolved else ResolutionStatus.UNRESOLVED,
            )
        ],
        verification=VerificationResult(status=VerificationStatus.SUPPORTED, confidence=0.9),
    )


# --- the check --------------------------------------------------------------------------------


def test_a_sentence_that_restates_its_evidence_is_supported() -> None:
    check = check_narrative(SectionKind.EXECUTIVE_SUMMARY, LINE, EVIDENCE)
    assert check is not None
    assert check.overall is TrustStatus.SUPPORTED
    assert [s.status for s in check.sentences] == [TrustStatus.SUPPORTED]


def test_an_invented_sentence_is_named_and_the_paragraph_is_only_partly_supported() -> None:
    text = f"{LINE} The consignment was insured by Northwind Assurance for its full value."
    check = check_narrative(SectionKind.EXECUTIVE_SUMMARY, text, EVIDENCE)
    assert check is not None
    assert check.overall is TrustStatus.PARTIALLY_SUPPORTED
    assert check.sentences[0].status is TrustStatus.SUPPORTED
    assert check.sentences[1].status is not TrustStatus.SUPPORTED


def test_a_value_no_cited_line_contains_is_named() -> None:
    """Lexically close to the evidence, and stating a figure nothing cites (A15)."""
    text = (
        "Shipment 4821 arrived at the Mumbai warehouse with 450 crates, received by Rahul Sharma."
    )
    check = check_narrative(SectionKind.REASONING, text, EVIDENCE)
    assert check is not None
    (sentence,) = check.sentences
    assert "450" in sentence.ungrounded
    assert sentence.status is not TrustStatus.SUPPORTED
    assert check.overall is not TrustStatus.SUPPORTED


def test_a_number_where_a_date_belongs_is_named() -> None:
    """BUG-021's claim, in prose."""
    check = check_narrative(
        SectionKind.EXECUTIVE_SUMMARY,
        "Shipment 4821 arrived at the Mumbai warehouse on 4821.",
        EVIDENCE,
    )
    assert check is not None
    assert "4821" in check.sentences[0].ungrounded


def test_no_narrative_no_check() -> None:
    assert check_narrative(SectionKind.REASONING, "   ", EVIDENCE) is None


def test_the_evidence_is_the_cited_resolved_lines_each_once() -> None:
    text = {"shipment_report_a.txt:r1": LINE, "other.txt:r9": "Unrelated."}
    findings = [
        _finding("shipment_report_a.txt:r1"),
        _finding("shipment_report_a.txt:r1"),
        _finding("ghost.txt:r3", resolved=False),
    ]
    assert evidence_for(findings, text) == [
        EvidenceText(source="shipment_report_a.txt:r1", content=LINE)
    ]


def test_member_4s_overall_rule_is_unchanged_by_the_refactor() -> None:
    supported, insufficient = TrustStatus.SUPPORTED, TrustStatus.INSUFFICIENT_EVIDENCE
    assert overall_status([supported, supported]) is supported
    assert overall_status([supported, TrustStatus.CONTRADICTED]) is TrustStatus.CONTRADICTED
    assert overall_status([supported, insufficient]) is TrustStatus.PARTIALLY_SUPPORTED
    assert overall_status([insufficient]) is insufficient
    assert overall_status([TrustStatus.UNSUPPORTED, insufficient]) is TrustStatus.UNSUPPORTED
    assert evaluate_answer(LINE, EVIDENCE).overall is supported


# --- inside synthesis -------------------------------------------------------------------------


def _engine(summary: str, reasoning: str) -> SynthesisEngine:
    narrative = json.dumps({"executive_summary": summary, "reasoning": reasoning})
    return SynthesisEngine(EchoProvider(responses={"synthesis": [narrative]}))


async def _synthesize(engine: SynthesisEngine, text: dict[str, str] | None, emit: object = None):
    return await engine.synthesize(
        run_id=new_run_id(),
        objective=Objective(text="When did Shipment 4821 arrive?"),
        findings=[_finding("shipment_report_a.txt:r1")],
        gaps=[],
        observations=[],
        execution=ExecutionSummary(tasks_planned=3, tasks_completed=3),
        emit=emit,
        evidence_text=text,
    )


async def test_the_report_carries_the_check_and_says_so_on_the_event_stream() -> None:
    sink = MemoryEventSink()
    emitter = RunEventEmitter(EventBus([sink]), new_run_id())
    invented = "The consignment was insured by Northwind Assurance for its full value."
    report = await _synthesize(
        _engine(LINE, invented), {"shipment_report_a.txt:r1": LINE}, emit=emitter
    )

    by_section = {c.section: c for c in report.narrative_checks}
    assert by_section[SectionKind.EXECUTIVE_SUMMARY].overall is TrustStatus.SUPPORTED
    assert by_section[SectionKind.REASONING].overall is not TrustStatus.SUPPORTED
    # Reported, not rewritten: the model's paragraph is in the report as written.
    reasoning = next(s for s in report.sections if s.kind is SectionKind.REASONING)
    assert reasoning.narrative == invented

    (event,) = sink.of_type(EventType.REPORT_EVALUATED)
    assert event.payload["sentences"] == 2
    assert event.payload["not_supported"] == 1

    markdown = to_markdown(report)
    assert "## How grounded the narrative is" in markdown
    assert "Northwind Assurance" in markdown.split("## How grounded the narrative is")[1]
    assert "NARRATIVE CHECK" in to_text(report)


async def test_without_line_text_there_is_no_check_and_no_event() -> None:
    sink = MemoryEventSink()
    emitter = RunEventEmitter(EventBus([sink]), new_run_id())
    report = await _synthesize(_engine(LINE, LINE), None, emit=emitter)
    assert report.narrative_checks == []
    assert sink.of_type(EventType.REPORT_EVALUATED) == []
    assert "How grounded" not in to_markdown(report)
