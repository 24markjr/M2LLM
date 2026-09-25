"""The relevance gate — a supported claim that does not answer the objective.

This is the fix for a defect the evaluation suite measured, not one anyone predicted.
Asked whether a report contradicts itself, the agent reported "the approved completion
date is 30 April 2026": true, correctly cited, and not an answer. Verification passed it
because verification asks whether the evidence supports the claim, and the evidence did.

Nothing in the pipeline asked whether the claim answered the question. This gate does.
"""

from __future__ import annotations

import json

from app.core.events import EventBus, MemoryEventSink, RunEventEmitter
from app.intelligence.reasoning.engine import ReasoningEngine
from app.llm.echo import EchoProvider
from app.schemas.common import new_run_id
from app.schemas.event import EventType
from app.schemas.execution import Observation
from app.schemas.objective import Objective

OBSERVATIONS = [
    Observation(
        task_id="task_001",
        task_type="extract_timeline",
        content="approved completion date 2026-04-30",
        sources=["report.txt:r1"],
    ),
    Observation(
        task_id="task_002",
        task_type="extract_timeline",
        content="delivery completed 2026-05-14",
        sources=["finance.txt:r1"],
    ),
]

OBJECTIVE = Objective(text="Determine whether the completion dates conflict.")


def _findings(*claims: tuple[str, list[str]]) -> str:
    return json.dumps({"findings": [{"claim": c, "citations": refs} for c, refs in claims]})


def _verdicts(*pairs: tuple[int, bool]) -> str:
    return json.dumps(
        {
            "verdicts": [
                {"index": i, "keep": keep, "reason": "" if keep else "restates a source"}
                for i, keep in pairs
            ]
        }
    )


def _engine(reasoning: list[str], relevance: list[str]) -> ReasoningEngine:
    return ReasoningEngine(EchoProvider(responses={"reasoning": reasoning, "relevance": relevance}))


def _emitter() -> tuple[RunEventEmitter, MemoryEventSink]:
    memory = MemoryEventSink()
    return RunEventEmitter(EventBus([memory]), new_run_id()), memory


# --- the defect this exists to prevent -----------------------------------------


async def test_a_supported_restatement_is_not_a_finding() -> None:
    """The measured confabulation, reproduced.

    The claim is true and its citation resolves. It is still not an answer to the
    objective, and an agent that reports it has not investigated anything.
    """
    engine = _engine(
        [_findings(("The approved completion date is 30 April 2026", ["report.txt:r1"]))],
        [_verdicts((1, False))],
    )

    findings = await engine.derive_findings(OBJECTIVE, OBSERVATIONS)

    assert findings == [], "a restatement of the source survived the gate"


async def test_a_claim_that_answers_the_objective_survives() -> None:
    """The gate must not simply suppress everything."""
    engine = _engine(
        [
            _findings(
                (
                    "The approved date of 30 April 2026 conflicts with the 14 May 2026 delivery",
                    ["report.txt:r1", "finance.txt:r1"],
                )
            )
        ],
        [_verdicts((1, True))],
    )

    findings = await engine.derive_findings(OBJECTIVE, OBSERVATIONS)

    assert len(findings) == 1
    assert "conflicts" in findings[0].claim


async def test_the_gate_keeps_and_drops_within_one_batch() -> None:
    """Relevance is judged per claim, in a single call."""
    engine = _engine(
        [
            _findings(
                ("The approved completion date is 30 April 2026", ["report.txt:r1"]),
                ("The two dates conflict by 14 days", ["report.txt:r1", "finance.txt:r1"]),
                ("The project is a data platform", ["report.txt:r1"]),
            )
        ],
        [_verdicts((1, False), (2, True), (3, False))],
    )

    findings = await engine.derive_findings(OBJECTIVE, OBSERVATIONS)

    assert [f.claim for f in findings] == ["The two dates conflict by 14 days"]


async def test_dropping_everything_is_a_valid_verdict() -> None:
    """A negative scenario's correct answer is no findings at all."""
    engine = _engine(
        [
            _findings(
                ("The approved completion date is 30 April 2026", ["report.txt:r1"]),
                ("The project is scheduled for Q2 2026", ["report.txt:r1"]),
            )
        ],
        [_verdicts((1, False), (2, False))],
    )

    assert await engine.derive_findings(OBJECTIVE, OBSERVATIONS) == []


# --- the gate is a filter, not a gatekeeper ------------------------------------


async def test_the_gate_fails_open() -> None:
    """If the check cannot run, findings pass through to verification.

    Silently discarding everything because a filter broke would turn one failed call into
    an investigation that reports nothing - the same output as an honest empty result,
    and indistinguishable from it.
    """
    engine = _engine(
        [_findings(("The two dates conflict by 14 days", ["report.txt:r1"]))],
        [],  # no fixture: the gate's call raises
    )

    findings = await engine.derive_findings(OBJECTIVE, OBSERVATIONS)

    assert len(findings) == 1, "a broken gate must not swallow findings"


async def test_no_candidates_means_no_gate_call() -> None:
    """Nothing to judge, so nothing is spent judging it."""
    engine = _engine([_findings()], [])

    assert await engine.derive_findings(OBJECTIVE, OBSERVATIONS) == []


# --- the drop is on the record -------------------------------------------------


async def test_every_discarded_claim_is_recorded() -> None:
    """A run is reconstructable from its events (invariant 4). A claim that vanished with
    no event would be indistinguishable from one the model never produced."""
    emitter, memory = _emitter()
    engine = _engine(
        [_findings(("The approved completion date is 30 April 2026", ["report.txt:r1"]))],
        [_verdicts((1, False))],
    )

    await engine.derive_findings(OBJECTIVE, OBSERVATIONS, emit=emitter)

    discarded = memory.of_type(EventType.FINDING_DISCARDED)
    assert len(discarded) == 1
    assert "30 April 2026" in str(discarded[0].payload["claim"])
    assert discarded[0].payload["reason"], "the reason it was dropped is recorded"


# --- a claim of conflict must cite both sides -----------------------------------
#
# The relevance gate asks a model whether a claim answers the objective, and at 4B that judgement
# is not reliable enough to be the only defence. Tuned to keep borderline claims it let
# restatements through; tuned to drop them it suppressed real contradictions. One model call cannot
# hold both ends of that trade, so the part that can be decided structurally is.


def _intent(*operations: str) -> object:
    from app.schemas.intent import Intent, Operation, RequiredOperation

    return Intent(
        goal="check",
        objective="check the reports",
        required_operations=[RequiredOperation(operation=Operation(op)) for op in operations],
    )


async def test_a_comparative_objective_drops_a_single_locator_claim() -> None:
    """The measured confabulation. A contradiction needs two things in tension, so a claim
    resting on one locator is a restatement of it - whatever the claim says."""
    engine = _engine(
        [_findings(("The approved completion date is 30 April 2026", ["report.txt:r1"]))],
        [_verdicts((1, True))],  # the gate kept it; the structural rule must not
    )

    findings = await engine.derive_findings(
        OBJECTIVE, OBSERVATIONS, intent=_intent("detect_inconsistencies")
    )

    assert findings == [], "a one-sided claim survived a comparative objective"


async def test_a_comparative_objective_keeps_a_claim_that_cites_both_sides() -> None:
    """The rule must not suppress the finding the run exists to produce."""
    engine = _engine(
        [
            _findings(
                (
                    "The approved date of 30 April conflicts with the 14 May delivery",
                    ["report.txt:r1", "finance.txt:r1"],
                )
            )
        ],
        [_verdicts((1, True))],
    )

    findings = await engine.derive_findings(
        OBJECTIVE, OBSERVATIONS, intent=_intent("detect_inconsistencies")
    )

    assert len(findings) == 1
    assert findings[0].resolved_evidence_count == 2


async def test_an_extraction_objective_keeps_a_single_locator_claim() -> None:
    """This is why the rule reads the intent rather than the claim.

    `aurora_timeline_only` asks to *extract* the timeline, and there a single-locator finding is
    exactly the answer. The same claim is an answer to one objective and noise in another.
    """
    engine = _engine(
        [_findings(("The approved completion date is 30 April 2026", ["report.txt:r1"]))],
        [_verdicts((1, True))],
    )

    findings = await engine.derive_findings(
        OBJECTIVE, OBSERVATIONS, intent=_intent("extract_timeline")
    )

    assert len(findings) == 1, "extraction objectives are answered by single-source facts"


async def test_a_claim_with_an_unresolved_citation_is_kept_and_marked() -> None:
    """The structural rule must not become an exception to "never drop, always mark".

    Measured: the first version of this rule dropped "Document A gives 30 April, document B gives
    14 May" - a real contradiction whose citations happened not to resolve because the model wrote
    placeholder document names. Dropping it hid a model problem behind a clean-looking result.

    Only a claim that is *fully supported* by too few sources is a restatement. One whose citations
    failed to resolve is kept, marked, and rejected by verification - visibly.
    """
    engine = _engine(
        [_findings(("The dates conflict.", ["report.txt:r1", "ghost.txt:r99"]))],
        [_verdicts((1, True))],
    )

    findings = await engine.derive_findings(
        OBJECTIVE, OBSERVATIONS, intent=_intent("detect_inconsistencies")
    )

    assert len(findings) == 1, "a claim with unresolved evidence must be reported, not hidden"
    finding = findings[0]
    assert finding.resolved_evidence_count == 1
    assert len(finding.evidence) == 2, "the unresolvable citation is kept on the record"
    assert finding.confidence.value < 0.5, "and it cannot present as confident"


async def test_no_intent_means_no_structural_filtering() -> None:
    """Callers that do not know the intent get the previous behaviour rather than a silent drop."""
    engine = _engine(
        [_findings(("The approved completion date is 30 April 2026", ["report.txt:r1"]))],
        [_verdicts((1, True))],
    )

    findings = await engine.derive_findings(OBJECTIVE, OBSERVATIONS)

    assert len(findings) == 1


async def test_a_dropped_restatement_is_recorded_with_its_reason() -> None:
    """A claim that vanished with no event is indistinguishable from one never produced."""
    emitter, memory = _emitter()
    engine = _engine(
        [_findings(("The approved completion date is 30 April 2026", ["report.txt:r1"]))],
        [_verdicts((1, True))],
    )

    await engine.derive_findings(
        OBJECTIVE, OBSERVATIONS, emit=emitter, intent=_intent("detect_inconsistencies")
    )

    discarded = memory.of_type(EventType.FINDING_DISCARDED)
    assert len(discarded) == 1
    assert "two sides" in str(discarded[0].payload["reason"])
