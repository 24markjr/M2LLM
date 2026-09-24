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
