"""v4 Phase 2: the model reads the whole prompt, and small documents are read whole."""

from __future__ import annotations

from typing import Any

import pytest

from app.intelligence.reasoning.engine import EvidenceBinder, ReasoningEngine
from app.intelligence.reasoning.whole import WHOLE_DOCUMENT, line_at, whole_documents
from app.llm.ollama import OllamaProvider
from app.llm.provider import CompletionRequest
from app.schemas.execution import Observation

DOCS = {
    "ledger.txt": "Orion ledger\n\nApproved budget: 250,000\nRecorded spend: 287,500\n",
    "auth.log": "4624 logon svc_admin from srv-db to srv-file via PsExec\n",
}


async def test_every_call_sets_the_context_window(monkeypatch: pytest.MonkeyPatch) -> None:
    """Ollama's default window is 2,048 tokens and it drops the start of a longer prompt."""
    sent: dict[str, Any] = {}

    async def fake_post(self: OllamaProvider, path: str, body: dict[str, Any]) -> dict[str, Any]:
        sent.update(body)
        return {"response": "ok", "done_reason": "stop"}

    monkeypatch.setattr(OllamaProvider, "_post", fake_post)
    await OllamaProvider().complete(CompletionRequest(prompt="hello", role="test"))
    assert sent["options"]["num_ctx"] >= 8192


def test_small_documents_are_read_whole_with_every_line_citable() -> None:
    whole = whole_documents(DOCS, task_id="task_001", budget_tokens=3000)
    assert whole is not None and whole.task_type == WHOLE_DOCUMENT
    assert whole.sources == ["auth.log:r1", "ledger.txt:r1", "ledger.txt:r3", "ledger.txt:r4"]
    assert "[ledger.txt:r4] Recorded spend: 287,500" in whole.content
    assert line_at(whole, "auth.log:r1").endswith("via PsExec")


def test_documents_too_large_to_read_whole_are_left_to_the_tools() -> None:
    assert whole_documents(DOCS, task_id="task_001", budget_tokens=10) is None
    assert whole_documents({}, task_id="task_001", budget_tokens=3000) is None


def test_a_citation_of_a_whole_document_line_binds_to_that_line_only() -> None:
    whole = whole_documents(DOCS, task_id="task_001", budget_tokens=3000)
    assert whole is not None
    refs, evidence = EvidenceBinder([whole]).bind(["ledger.txt:r3", "ledger.txt:r9"])
    assert refs[0].is_resolved and not refs[1].is_resolved
    assert evidence[0].content == "ledger.txt:r3: Approved budget: 250,000"


def test_the_prompt_shows_each_line_once() -> None:
    whole = whole_documents(DOCS, task_id="task_001", budget_tokens=3000)
    assert whole is not None
    tool = Observation(task_id="task_002", task_type="extract_budget", sources=["ledger.txt:r3"])
    text = ReasoningEngine._describe([tool, whole])
    assert text.count("Recorded spend: 287,500") == 1
    assert "  - ledger.txt:r3" in text  # the tool's own source is still listed


# --- figures: Indian grouping, and arithmetic redone by code ----------------------------------


def test_indian_grouping_is_one_figure() -> None:
    from decimal import Decimal

    from app.intelligence.temporal import find_figures
    from app.tools.builtin import _amounts

    assert [v for _, v in find_figures("Rs 4,80,000 against 3,20,000")] == [
        Decimal(480000),
        Decimal(320000),
    ]
    assert [v for _, v in find_figures("1,25,00,000 and 1,234,567.50")] == [
        Decimal(12500000),
        Decimal("1234567.50"),
    ]
    assert _amounts("Paid Rs 4,80,000; approved 3,20,000; 450,000") == [
        "4,80,000",
        "3,20,000",
        "450,000",
    ]


@pytest.mark.parametrize(
    ("claim", "checked", "holds"),
    [
        ("a budget of 250,000 and spend of 287,500, an overrun of 37,500", True, True),
        ("a budget of 250,000 and spend of 287,500, an overrun of 47,500", True, False),
        ("Rs 4,80,000 paid against 3,20,000 approved, exceeding it by 1,60,000", True, True),
        ("the total of 120,000 and 80,000 is 200,000", True, True),
        ("the total of 120,000 and 80,000 is 210,000", True, False),
        ("the spend of 450,000 exceeds the approved 380,000", False, True),
        ("the reports differ: 30 April and 14 May", False, True),
    ],
)
def test_a_claims_arithmetic_is_redone(claim: str, checked: bool, holds: bool) -> None:
    from app.intelligence.arithmetic import check_arithmetic

    result = check_arithmetic(claim)
    assert (result.checked, result.holds) == (checked, holds), result.reason


def test_wrong_arithmetic_costs_confidence_and_says_why() -> None:
    from app.intelligence.confidence import assess
    from app.schemas.common import SourceLocator
    from app.schemas.evidence import EvidenceRef, ResolutionStatus
    from app.schemas.finding import Finding, FindingClassification

    ref = EvidenceRef(
        evidence_id="E-001",
        locator=SourceLocator(document_id="ledger.txt", row=3),
        resolution=ResolutionStatus.RESOLVED,
    )

    def finding(claim: str) -> Finding:
        return Finding(
            finding_id="F-001",
            claim=claim,
            evidence=[ref],
            classification=FindingClassification.FACT,
        )

    right = assess(finding("budget 250,000, spend 287,500, an overrun of 37,500"))
    wrong = assess(finding("budget 250,000, spend 287,500, an overrun of 47,500"))
    assert wrong.value < right.value
    penalty = next(f for f in wrong.factors if f.name == "arithmetic")
    assert "287,500 - 250,000 = 37,500" in penalty.reason


# --- the entailment model, and the gates that dropped right answers --------------------------


def _request(claim: str) -> Any:
    from app.schemas.verification import VerificationRequest

    return VerificationRequest(
        claim=claim,
        evidence_content={
            "budget.csv:r2": "budget.csv:r2: migration,450000,no",
            "finance.txt:r3": "finance.txt:r3: Total Helix migration spend: 450,000",
        },
    )


async def _composite_with(monkeypatch: pytest.MonkeyPatch, model: str, nli: Any) -> Any:
    from app.integrations import verification
    from app.intelligence.trust import nli as nli_module
    from app.schemas.verification import (
        IssueType,
        VerificationIssue,
        VerificationResult,
        VerificationStatus,
    )

    class Fixed:
        async def verify(self, request: Any) -> VerificationResult:
            status = VerificationStatus(model)
            issues = (
                [VerificationIssue(issue_type=IssueType.EVIDENCE_MISMATCH, description="no")]
                if status is VerificationStatus.UNSUPPORTED
                else []
            )
            return VerificationResult(
                status=status, confidence=0.5, verifier="model", issues=issues
            )

    async def fake(premise: str, hypothesis: str) -> Any:
        return nli

    monkeypatch.setattr(nli_module, "entailment", fake)
    return verification.CompositeVerifier(Fixed(), verification.LexicalVerifier())


async def test_a_confident_contradiction_lowers_an_approval(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.intelligence.trust.nli import Entailment

    verifier = await _composite_with(
        monkeypatch, "SUPPORTED", Entailment(entailment=0.02, neutral=0.06, contradiction=0.92)
    )
    result = await verifier.verify(_request("The Helix spend of 450,000 was approved."))
    assert result.status.value == "PARTIALLY_SUPPORTED"
    assert "entailment model" in result.issues[-1].description
    assert [o.verifier for o in result.opinions][-1] == "nli"


async def test_entailment_decides_only_where_the_model_could_not(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.intelligence.trust.nli import Entailment

    sure = Entailment(entailment=0.9, neutral=0.05, contradiction=0.05)
    undecided = await _composite_with(monkeypatch, "INCONCLUSIVE", sure)
    result = await undecided.verify(_request("Helix migration spend was 450,000."))
    assert result.status.value == "SUPPORTED" and result.degraded
    rejected = await _composite_with(monkeypatch, "UNSUPPORTED", sure)
    result = await rejected.verify(_request("Helix migration spend was 450,000."))
    assert result.status.value == "UNSUPPORTED"  # never overrides a rejection


def test_a_status_contrast_on_one_figure_is_not_agreement() -> None:
    from app.intelligence.trust.specifics import single_value

    status = "budget.csv shows 450,000 was not approved; finance.txt spent 450,000"
    assert single_value(status) == ""
    assert single_value("states 30 April 2026 at r10 and again 30 April 2026 at r15")
    assert single_value("the notes give 250,000 and the ledger gives 250,000") == "250,000"


def test_an_uncited_claim_is_cited_by_its_own_values() -> None:
    from app.intelligence.reasoning.whole import cite_by_values

    docs = {
        "project_report.txt": "Approved completion date: 30 April 2026\n",
        "financial_report.txt": "Latest milestone: 14 May 2026\n",
    }
    whole = whole_documents(docs, task_id="task_001", budget_tokens=3000)
    assert whole is not None
    claim = "The approved completion is 30 April 2026 but the milestone is 14 May 2026"
    assert cite_by_values(claim, whole) == ["project_report.txt:r1", "financial_report.txt:r1"]
    assert cite_by_values("It ends on 1 June 2026 and 14 May 2026", whole) == []


# --- hybrid search ---------------------------------------------------------------------------


def _chunk(chunk_id: str, text: str, score: float = 0.0) -> Any:
    from app.intelligence.context.manager import Chunk, RetrievedChunk
    from app.schemas.common import SourceLocator

    return RetrievedChunk(
        chunk=Chunk(
            chunk_id=chunk_id, locator=SourceLocator(document_id="d.txt", row=1), text=text
        ),
        score=score,
    )


def test_bm25_finds_the_exact_identifier() -> None:
    from app.intelligence.context.hybrid import bm25, terms

    assert terms("Was INV-1042 paid to srv-db?") == ["inv-1042", "paid", "srv-db"]
    passages = [
        _chunk("a", "Invoice INV-1024 was paid on 2 March."),
        _chunk("b", "Invoice INV-1042 was paid twice on 3 March."),
        _chunk("c", "The weather was fine."),
    ]
    ranked = bm25("INV-1042", passages)
    assert [p.chunk.chunk_id for p in ranked] == ["b"] and ranked[0].score == 1.0


def test_fusion_lifts_a_passage_both_lists_agree_on() -> None:
    from app.intelligence.context.hybrid import fuse

    meaning = [_chunk("a", "x", 0.9), _chunk("b", "y", 0.8), _chunk("c", "z", 0.7)]
    words = [_chunk("c", "z"), _chunk("d", "w")]
    fused = fuse([meaning, words], 3)
    assert [h.chunk.chunk_id for h in fused] == ["c", "a", "b"]
    assert fused[0].score == 0.7  # meaning's similarity is kept where it has one


async def test_hybrid_search_finds_what_meaning_alone_ranks_low() -> None:
    from app.integrations.context import ingest_document, search_store
    from app.intelligence.context.store import MemoryContextStore
    from app.llm.echo import EchoProvider

    store = MemoryContextStore()
    text = "\n".join(
        [f"Routine note {i} about deliveries and weather." for i in range(30)]
        + ["Invoice INV-1042 was paid twice to Blue Harbor."]
    )
    await ingest_document(store, EchoProvider(), workspace_id="w", document_id="log.txt", text=text)
    hits = await search_store(store, EchoProvider(), workspace_id="w", query="INV-1042", k=3)
    assert any("INV-1042" in h.chunk.text for h in hits)
