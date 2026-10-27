"""v4 Phase 3: the investigation conversation - a scripted five-turn investigation.

The model's steps are scripted; the tools, the citation resolution, the verification hand-off, the
re-checks and the thread's storage are the real ones.
"""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
from httpx import ASGITransport, AsyncClient

from app.conversation import service, store, tools
from app.conversation.models import StopReason
from app.conversation.service import AnswerClaim, Step
from app.conversation.tools import CaseFinding, CaseMaterial
from app.schemas.common import SourceLocator
from app.schemas.evidence import EvidenceRef, ResolutionStatus
from app.schemas.finding import Finding
from app.schemas.verification import (
    IssueType,
    VerificationIssue,
    VerificationResult,
    VerificationStatus,
)

CASE = "CASE-2026-00001"
MODEL: Any = object()  # never called: the model's steps are scripted
DOCS = {
    "project_report.txt": "Project Aurora\nApproved completion date: 30 April 2026\n"
    "Budget 380,000\n",
    "financial_report.txt": "Finance\nLatest milestone: 14 May 2026\nSpend: 450,000\n",
}


def _finding() -> Finding:
    return Finding(
        finding_id="F-001",
        claim="The completion dates differ: 30 April 2026 and 14 May 2026",
        evidence=[
            EvidenceRef(
                evidence_id="E-001",
                locator=SourceLocator(document_id="project_report.txt", row=2),
                resolution=ResolutionStatus.RESOLVED,
            )
        ],
        verification=VerificationResult(
            status=VerificationStatus.PARTIALLY_SUPPORTED,
            confidence=0.5,
            issues=[VerificationIssue(issue_type=IssueType.OVERSTATED_CLAIM, description="x")],
        ),
    )


class LineVerifier:
    """Supported when every date and figure of the claim is on its cited lines; else unsupported."""

    async def verify(self, request: Any) -> VerificationResult:
        from app.intelligence.trust.specifics import ungrounded_specifics
        from app.schemas.trust import EvidenceText

        pool = [EvidenceText(source=k, content=v) for k, v in request.evidence_content.items()]
        if pool and not ungrounded_specifics(request.claim, pool):
            return VerificationResult(status=VerificationStatus.SUPPORTED, confidence=0.9)
        return VerificationResult(
            status=VerificationStatus.UNSUPPORTED,
            confidence=0.1,
            issues=[VerificationIssue(issue_type=IssueType.NO_EVIDENCE, description="not cited")],
        )


@pytest.fixture
def script(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Iterator[dict[str, Any]]:
    """Scripted model steps, the prompts it was shown, and a case's material."""
    monkeypatch.setattr(store, "_path", lambda case_id: tmp_path / f"{case_id}.json")
    state: dict[str, Any] = {"steps": [], "prompts": []}
    material = CaseMaterial(
        case_id=CASE,
        documents=dict(DOCS),
        findings=[CaseFinding(run_id="run_0123456789ab", finding=_finding())],
    )

    async def fake_gather(case_id: str) -> CaseMaterial:
        return material.model_copy(deep=True)

    async def fake_generate(provider: Any, schema: Any, prompt: str, **_: Any) -> Step:
        state["prompts"].append(prompt)
        return state["steps"].pop(0)

    monkeypatch.setattr(service, "gather", fake_gather)
    monkeypatch.setattr(service, "generate_structured", fake_generate)
    monkeypatch.setattr(service, "build_verification_provider", lambda _p: LineVerifier())
    state["material"] = material
    yield state


async def test_a_five_turn_investigation_keeps_context_and_verifies_every_claim(
    script: dict[str, Any],
) -> None:
    # Turn 1: search, then answer citing the line it found.
    script["steps"] += [
        Step(action="search_evidence", arguments={"query": "completion date"}),
        Step(
            action="answer",
            claims=[
                AnswerClaim(
                    text="Aurora was due on 30 April 2026.", citations=["project_report.txt:r2"]
                )
            ],
        ),
    ]
    thread = await service.converse(CASE, "When was Aurora due?", object(), actor="a@x.test")  # type: ignore[arg-type]
    first = thread.turns[-1]
    assert first.stop_reason is StopReason.ANSWERED
    assert first.steps[0].tool == "search_evidence"
    assert (
        "[project_report.txt:r2] Approved completion date: 30 April 2026" in first.steps[0].result
    )
    assert [(c.status, c.citations) for c in first.claims] == [
        ("SUPPORTED", ["project_report.txt:r2"])
    ]

    # Turn 2: "it" refers to turn 1 - the history the model is shown carries the earlier answer.
    script["steps"] += [
        Step(
            action="answer",
            claims=[
                AnswerClaim(
                    text="The finance report gives 14 May 2026.",
                    citations=["financial_report.txt:r2"],
                )
            ],
        )
    ]
    thread = await service.converse(CASE, "Does finance agree with it?", object())  # type: ignore[arg-type]
    assert (
        "Aurora was due on 30 April 2026. [SUPPORTED; project_report.txt:r2]"
        in script["prompts"][-1]
    )
    assert thread.turns[-1].claims[0].status == "SUPPORTED"

    # Turn 3: a claim citing the wrong line is shown, but as not supported - never as an answer.
    script["steps"] += [
        Step(
            action="answer",
            claims=[
                AnswerClaim(text="Spend was 450,000.", citations=["project_report.txt:r3"]),
                AnswerClaim(text="Spend was approved.", citations=["nowhere.txt:r9"]),
            ],
        )
    ]
    thread = await service.converse(CASE, "What was spent?", object())  # type: ignore[arg-type]
    statuses = [c.status for c in thread.turns[-1].claims]
    assert statuses == ["UNSUPPORTED", "UNVERIFIED"]

    # Turn 4: re-check a finding by id - no model loop, a before/after record.
    thread = await service.converse(CASE, "Recheck F-001", object())  # type: ignore[arg-type]
    turn = thread.turns[-1]
    assert turn.stop_reason is StopReason.RECHECKED
    assert [(r.finding_id, r.before, r.after, r.changed) for r in turn.rechecks] == [
        ("F-001", "PARTIALLY_SUPPORTED", "UNSUPPORTED", True)
    ]

    # Turn 5: the tool budget runs out; the model must answer from what it has.
    script["steps"] += [
        Step(action="search_evidence", arguments={"query": f"budget {i}"})
        for i in range(service.MAX_TOOL_CALLS)
    ] + [Step(action="search_evidence", arguments={"query": "more"})]
    thread = await service.converse(CASE, "Dig through everything about the budget.", object())  # type: ignore[arg-type]
    last = thread.turns[-1]
    assert last.stop_reason is StopReason.STEP_LIMIT and len(last.steps) == service.MAX_TOOL_CALLS
    assert "tool budget" in last.text

    # The whole thread was kept, in order, and reads back from disk.
    kept = store.load(CASE)
    assert [t.role for t in kept.turns] == ["user", "assistant"] * 5
    assert kept.turns[6].findings_referred == ["F-001"]


async def test_ask_user_stops_and_puts_the_question(script: dict[str, Any]) -> None:
    script["steps"] += [Step(action="ask_user", question="Which contract do you mean?")]
    thread = await service.converse(CASE, "Check the contract.", object())  # type: ignore[arg-type]
    turn = thread.turns[-1]
    assert turn.stop_reason is StopReason.ASKED_USER
    assert turn.question == "Which contract do you mean?" and not turn.claims


async def test_an_uncited_claim_is_cited_by_its_values(script: dict[str, Any]) -> None:
    script["steps"] += [
        Step(action="answer", claims=[AnswerClaim(text="The milestone is 14 May 2026.")])
    ]
    thread = await service.converse(CASE, "When is the milestone?", object())  # type: ignore[arg-type]
    claim = thread.turns[-1].claims[0]
    assert claim.citations == ["financial_report.txt:r2"] and claim.status == "SUPPORTED"


def test_the_tools() -> None:
    material = CaseMaterial(case_id=CASE, documents=dict(DOCS))
    assert tools.read_span(material, "financial_report.txt", 2, 3).splitlines() == [
        "[financial_report.txt:r2] Latest milestone: 14 May 2026",
        "[financial_report.txt:r3] Spend: 450,000",
    ]
    assert "no document" in tools.read_span(material, "ghost.txt", 1, 2)
    assert tools.calculate("450,000 - 380,000") == "450,000 - 380,000 = 70,000"
    assert "cannot calculate" in tools.calculate("__import__('os')")
    assert tools.compare_values("450,000", "380,000") == "450,000 is larger than 380,000 by 70,000"
    assert "different dates" in tools.compare_values("30 April 2026", "14 May 2026")
    assert "no tool" in tools.run_tool(material, "rm_rf", {})


async def test_the_conversation_routes_are_per_case_and_organisation(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    from app.api.app import create_app

    monkeypatch.setattr(store, "_path", lambda case_id: tmp_path / f"{case_id}.json")
    async with AsyncClient(transport=ASGITransport(app=create_app()), base_url="http://t") as c:
        assert (await c.get(f"/api/v1/cases/{CASE}/conversation")).status_code == 404
        case_id = (await c.post("/api/v1/cases", json={"title": "Aurora"})).json()["case_id"]
        thread = (await c.get(f"/api/v1/cases/{case_id}/conversation")).json()
        assert thread == {"case_id": case_id, "turns": []}
