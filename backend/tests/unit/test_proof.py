"""Phase U7: the verification receipt, and the same question put to the plain model.

The receipt is counted from the run and hashed over itself, so it must change when anything it
vouches for changes. The comparison scores both answers with one checker against one evidence pool,
so an invented figure is caught on whichever side states it.
"""

from __future__ import annotations

import pytest
from httpx import ASGITransport, AsyncClient

from app.api.app import create_app
from app.api.registry import MissionRecord, get_registry
from app.intelligence import proof
from app.llm.echo import EchoProvider
from app.orchestration.mission import MissionResult, MissionStatus, Stage
from app.schemas.common import SourceLocator, new_run_id
from app.schemas.evidence import ClaimElement, EvidenceRef, ResolutionStatus
from app.schemas.finding import Finding
from app.schemas.objective import Objective
from app.schemas.verification import VerificationResult, VerificationStatus

TEXTS = {
    "project.txt": "Approved budget: 380,000.\nCompletion date: 30 April 2026.",
    "finance.txt": "Expenditure to date: 450,000.\nLatest milestone: 14 May 2026.",
}


def _finding(resolved: bool = True) -> Finding:
    return Finding(
        finding_id="F-001",
        claim="Expenditure of 450,000 exceeds the approved budget of 380,000.",
        evidence=[
            EvidenceRef(
                evidence_id="E-001",
                locator=SourceLocator(
                    document_id="finance.txt", document_name="finance.txt", row=1
                ),
                resolution=ResolutionStatus.RESOLVED if resolved else ResolutionStatus.UNRESOLVED,
            )
        ],
        elements=[ClaimElement(text="exceeds", supported=True)],
        verification=VerificationResult(status=VerificationStatus.SUPPORTED, confidence=0.9),
    )


def _receipt(texts: dict[str, str] = TEXTS) -> proof.Receipt:
    return proof.build_receipt(
        run_id="run_000000000001",
        question="Do the reports agree?",
        model="qwen3:4b",
        prompt_versions={"reasoning": 3, "intent": 2},
        started_at=None,
        finished_at=None,
        texts=texts,
        evidence={"finance.txt": "EV-1"},
        findings=[_finding()],
        report=None,
        tasks_planned=5,
        tasks_completed=5,
        gaps_open=0,
    )


# --- the receipt ---------------------------------------------------------------------------------


def test_the_receipt_hashes_each_file_and_counts_each_finding() -> None:
    receipt = _receipt()
    assert [d.name for d in receipt.documents] == ["finance.txt", "project.txt"]
    assert all(len(d.sha256) == 64 for d in receipt.documents)
    assert receipt.documents[0].evidence_id == "EV-1"
    finding = receipt.findings[0]
    assert (finding.verification, finding.citations, finding.citations_resolved) == (
        "SUPPORTED",
        1,
        1,
    )


def test_the_receipt_hash_is_stable_and_changes_with_what_it_vouches_for() -> None:
    assert _receipt().receipt_hash == _receipt().receipt_hash
    altered = {**TEXTS, "finance.txt": TEXTS["finance.txt"].replace("450,000", "460,000")}
    assert _receipt(altered).receipt_hash != _receipt().receipt_hash


# --- the comparison ------------------------------------------------------------------------------


def test_the_evidence_pool_is_every_non_blank_line_named_by_file_and_line() -> None:
    pool = proof.evidence_lines({"a.txt": "one\n\nthree"})
    assert [(e.source, e.content) for e in pool] == [("a.txt:1", "one"), ("a.txt:3", "three")]


def test_the_plain_prompt_says_when_the_files_were_cut() -> None:
    prompt, truncated = proof.baseline_prompt(
        "Q?", {"big.txt": "x" * (proof.MAX_BASELINE_CHARS + 10)}
    )
    assert truncated
    assert "Question: Q?" in prompt
    _, whole = proof.baseline_prompt("Q?", TEXTS)
    assert not whole


async def test_an_invented_figure_is_caught_on_the_plain_side() -> None:
    provider = EchoProvider(
        responses={"baseline": ['{"answer": "Expenditure to date was 520,000, above budget."}']}
    )
    comparison = await proof.compare(
        provider,
        run_id="run_000000000001",
        question="Do the reports agree?",
        texts=TEXTS,
        findings=[_finding()],
        report=None,
    )
    assert "520,000" in " ".join(comparison.plain.ungrounded)
    assert comparison.plain.tally.sentences == 1
    assert comparison.jarvis.cited_findings == 1
    assert comparison.evidence_lines == 4


# --- the routes ----------------------------------------------------------------------------------


def _record(status: MissionStatus) -> MissionRecord:
    record = MissionRecord(new_run_id(), Objective(text="Do the reports agree?"), list(TEXTS))
    record.status = status
    record.stage = Stage.DONE if status is MissionStatus.COMPLETED else Stage.EXECUTING
    record.texts = dict(TEXTS)
    record.result = MissionResult(
        run_id=record.run_id, objective=record.objective, findings=[_finding()]
    )
    get_registry()._missions[record.run_id] = record
    return record


async def _get(path: str) -> tuple[int, dict[str, object]]:
    async with AsyncClient(
        transport=ASGITransport(app=create_app()), base_url="http://t"
    ) as client:
        response = await client.get(path)
    return response.status_code, response.json()


async def test_a_receipt_waits_for_the_run_to_finish() -> None:
    record = _record(MissionStatus.RUNNING)
    status, body = await _get(f"/api/v1/missions/{record.run_id}/receipt")
    assert (status, body["error_code"]) == (409, "MISSION_NOT_FINISHED")


async def test_a_finished_run_has_a_receipt_and_says_when_no_comparison_was_asked() -> None:
    record = _record(MissionStatus.COMPLETED)
    status, body = await _get(f"/api/v1/missions/{record.run_id}/receipt")
    assert status == 200
    assert body["run_id"] == record.run_id
    assert len(str(body["receipt_hash"])) == 64

    status, body = await _get(f"/api/v1/missions/{record.run_id}/comparison")
    assert (status, body["error_code"]) == (404, "COMPARISON_NOT_RUN")


@pytest.fixture(autouse=True)
def _fresh_registry() -> None:
    from app.api.registry import reset_registry

    reset_registry()


def test_the_plain_answer_is_read_from_its_json_or_taken_as_written() -> None:
    assert proof.answer_of('{"answer": " It agrees. "}') == "It agrees."
    assert proof.answer_of("It agrees.") == "It agrees."
    assert proof.answer_of('["not", "an object"]') == '["not", "an object"]'
