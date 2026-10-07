"""BUG-032: a report states what its run could and could not examine.

From a real mission over twelve AURORA documents (run_9b03bd99041a): no findings, a confidence of
"None.", a Limitations section printing a placeholder string, and nothing saying that the knowledge
pass had read 12 of 191 sections, that five of seven searches had found nothing, or that all 22
candidate findings had been discarded before verification.
"""

from __future__ import annotations

import json

from app.intelligence.reasoning.engine import (
    DISCARD_IRRELEVANT,
    DISCARD_SINGLE_SOURCE,
    ReasoningEngine,
)
from app.intelligence.synthesis.engine import (
    SynthesisEngine,
    coverage_limitations,
    examined,
    no_confidence_line,
)
from app.llm.echo import EchoProvider
from app.schemas.common import new_run_id
from app.schemas.execution import Observation
from app.schemas.knowledge import ExtractionStats, KnowledgeSnapshot
from app.schemas.objective import AttachedDocument, Objective, ObjectiveScope
from app.schemas.result import ExecutionSummary, SectionKind

# The run's own numbers.
KNOWLEDGE = KnowledgeSnapshot(
    stats=ExtractionStats(
        documents=12,
        documents_read=1,
        chunks=191,
        chunks_skipped=179,
        failed_chunks=3,
        claims=86,
        ungrounded_claims=64,
    )
)
OBSERVATIONS = [
    Observation(
        task_id="task_001", task_type="process_documents", content="16", sources=["a.pdf:p1"]
    ),
    Observation(
        task_id="task_003", task_type="retrieve_evidence", content="8", sources=["a.pdf:p2"]
    ),
    *[
        Observation(task_id=f"task_00{n}", task_type=kind, content="0 matching passage(s)")
        for n, kind in [(4, "detect_inconsistencies"), (5, "compare_sources"), (6, "synthesize")]
    ],
    Observation(task_id="task_002", task_type="extract_claims", content="no extractions"),
]
DISCARDED = {DISCARD_SINGLE_SOURCE: 22}


def test_the_limitations_name_every_gap_in_coverage() -> None:
    texts = [
        lim.description for lim in coverage_limitations(KNOWLEDGE, OBSERVATIONS, DISCARDED, [])
    ]
    assert "The knowledge pass read 12 of 191 document section(s)" in texts[0]
    assert "the other 179 were not examined" in texts[0]
    assert texts[1] == "3 section(s) could not be read by the model"
    assert texts[2].startswith("64 of 86 extracted claim(s) were not found on their source line")
    assert texts[3].startswith("3 evidence-gathering step(s) found no matching passage")
    assert texts[4].startswith(
        "22 candidate finding(s) were discarded before verification - none survived"
    )
    assert "rested on one source" in texts[4]


def test_what_was_examined_is_stated_in_numbers() -> None:
    lines = examined(KNOWLEDGE, OBSERVATIONS, ExecutionSummary(documents_processed=12))
    assert lines == [
        "12 document(s) attached",
        "the knowledge pass read 12 of 191 section(s) across 1 of 12 document(s)",
        "2 of 5 evidence-gathering step(s) found matching passages",
    ]


def test_an_empty_confidence_explains_itself() -> None:
    assert "22 candidate(s) were proposed and discarded" in no_confidence_line(22)
    assert "nothing was proposed" in no_confidence_line(0)


async def test_the_report_states_its_limits_and_never_prints_a_placeholder() -> None:
    engine = SynthesisEngine(
        EchoProvider(
            responses={
                "synthesis": [json.dumps({"executive_summary": "Nothing.", "reasoning": ""})]
            }
        )
    )
    report = await engine.synthesize(
        run_id=new_run_id(),
        objective=Objective(
            text="Determine whether AURORA can be trusted for deployment.",
            scope=ObjectiveScope(documents=[AttachedDocument(document_id="a.pdf", name="a.pdf")]),
        ),
        findings=[],
        gaps=[],
        observations=OBSERVATIONS,
        execution=ExecutionSummary(tasks_planned=6, tasks_completed=6, documents_processed=12),
        knowledge=KNOWLEDGE,
        discarded=DISCARDED,
    )
    limitations = report.section(SectionKind.LIMITATIONS)
    confidence = report.section(SectionKind.CONFIDENCE)
    scope = report.section(SectionKind.INVESTIGATION_SCOPE)
    assert limitations is not None and confidence is not None and scope is not None
    assert not any("generated from run facts" in item for item in limitations.items)
    assert any("12 of 191" in item for item in limitations.items)
    assert confidence.items[0].startswith("No finding was established")
    assert "Examined: the knowledge pass read 12 of 191 section(s) across 1 of 12 document(s)" in (
        scope.items
    )


async def test_a_run_with_nothing_to_report_says_none_was_found() -> None:
    engine = SynthesisEngine(
        EchoProvider(
            responses={"synthesis": [json.dumps({"executive_summary": "x", "reasoning": ""})]}
        )
    )
    report = await engine.synthesize(
        run_id=new_run_id(),
        objective=Objective(text="Check the one short document for contradictions."),
        findings=[],
        gaps=[],
        observations=[],
        execution=ExecutionSummary(),
    )
    section = report.section(SectionKind.LIMITATIONS)
    assert section is not None and section.items == ["None found by the run's own checks."]


def test_reasoning_starts_with_nothing_discarded() -> None:
    engine = ReasoningEngine(EchoProvider())
    assert engine.discarded == {}
    engine.discarded[DISCARD_IRRELEVANT] += 1
    assert sum(engine.discarded.values()) == 1
