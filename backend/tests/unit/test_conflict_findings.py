"""BUG-031: which contradictions the graph found become findings directly."""

from __future__ import annotations

import pytest

from app.intelligence.reasoning.conflict_findings import claim_of, conflict_findings, reportable
from app.schemas.common import SourceLocator
from app.schemas.evidence import EvidenceRef, ResolutionStatus
from app.schemas.execution import Observation
from app.schemas.finding import Finding
from app.schemas.knowledge import ClaimConflict, ConflictKind, ConflictSide, KnowledgeSnapshot


def _conflict(
    attribute: str = "completion_date",
    kind: ConflictKind = ConflictKind.DATE,
    sources: tuple[str, str] = ("report.txt:r10", "finance.txt:r12"),
    values: tuple[str, str] = ("30 April 2026", "14 May 2026"),
    same_document: bool = False,
) -> ClaimConflict:
    return ClaimConflict(
        conflict_id="CON-001",
        entity_id="ENT-1",
        entity_name="Project Aurora",
        attribute=attribute,
        kind=kind,
        same_document=same_document,
        sides=[
            ConflictSide(value=values[0], claim_ids=["CLM-001"], sources=[sources[0]]),
            ConflictSide(value=values[1], claim_ids=["CLM-002"], sources=[sources[1]]),
        ],
    )


OBSERVATIONS = [
    Observation(
        task_id="task_001",
        task_type="extract_claims",
        content="1 conflict",
        sources=["report.txt:r10", "finance.txt:r12"],
    ),
]


@pytest.mark.parametrize(
    ("conflict", "expected"),
    [
        (_conflict(), True),
        (
            _conflict(kind=ConflictKind.NUMBER, attribute="budget", values=("380,000", "450,000")),
            True,
        ),
        # Text stays with reasoning; same-document pairs may be planned against actual.
        (_conflict(kind=ConflictKind.TEXT, attribute="manager", values=("Arjun", "Rahul")), False),
        (_conflict(same_document=True, sources=("report.txt:r10", "report.txt:r40")), False),
        # A document's own date differs between documents by nature (the BUG-027 trap).
        (_conflict(attribute="date"), False),
        (_conflict(attribute="report_date"), False),
        (_conflict(attribute="version", kind=ConflictKind.NUMBER, values=("1.2", "1.3")), False),
    ],
)
def test_only_checkable_cross_document_contradictions_are_reportable(
    conflict: ClaimConflict, expected: bool
) -> None:
    assert reportable(conflict) is expected


def test_the_claim_names_each_value_and_where_it_is_stated() -> None:
    assert claim_of(_conflict()) == (
        "The documents disagree on the completion date of Project Aurora: "
        "report.txt:r10 gives 30 April 2026; finance.txt:r12 gives 14 May 2026."
    )


def test_only_for_a_question_that_asks_for_a_comparison() -> None:
    knowledge = KnowledgeSnapshot(conflicts=[_conflict()])
    assert conflict_findings(knowledge, [], OBSERVATIONS, comparative=False) == []
    [finding] = conflict_findings(knowledge, [], OBSERVATIONS, comparative=True)
    assert finding.finding_id == "F-001" and finding.resolved_evidence_count == 2


def test_both_sides_must_resolve_against_what_the_run_retrieved() -> None:
    knowledge = KnowledgeSnapshot(conflicts=[_conflict()])
    one_side = [
        Observation(
            task_id="task_009", task_type="extract_claims", content="x", sources=["report.txt:r10"]
        )
    ]
    assert conflict_findings(knowledge, [], one_side, comparative=True) == []


def test_a_new_finding_never_reuses_an_existing_id() -> None:
    existing = Finding(
        finding_id="F-001",
        claim="Something else.",
        evidence=[
            EvidenceRef(
                evidence_id="E-001",
                locator=SourceLocator(document_id="other.txt", document_name="other.txt", row=1),
                resolution=ResolutionStatus.RESOLVED,
            )
        ],
    )
    [added] = conflict_findings(
        KnowledgeSnapshot(conflicts=[_conflict()]), [existing], OBSERVATIONS, comparative=True
    )
    assert added.finding_id == "F-002"


# --- BUG-030: graph copies, and findings resting on one document ---


@pytest.mark.parametrize(
    ("claim", "copy"),
    [
        ("AURORA.description = Automated Unified Reasoning and Optimization Architecture", True),
        ("XML / CSV.supported_formats = BOM ingestion, schedule export", True),
        ("Mazagon Dock Shipbuilders Limited (MDL).plm = PLM/ERP ecosystem", True),
        ("The SoW specifies no penetration testing before deployment.", False),
        ("Spend of 287,500 exceeds the approved 250,000.", False),
        ("Version 1.2 of the report = the final one", False),
    ],
)
def test_a_copied_graph_entry_is_recognised(claim: str, copy: bool) -> None:
    from app.intelligence.reasoning.engine import is_graph_copy

    assert is_graph_copy(claim) is copy


def test_a_finding_knows_when_it_rests_on_one_document() -> None:
    def ref(document: str, row: int) -> EvidenceRef:
        return EvidenceRef(
            evidence_id=f"E-{row:03d}",
            locator=SourceLocator(document_id=document, document_name=document, row=row),
            resolution=ResolutionStatus.RESOLVED,
        )

    one = Finding(finding_id="F-001", claim="x", evidence=[ref("a.txt", 1), ref("a.txt", 2)])
    two = Finding(finding_id="F-002", claim="y", evidence=[ref("a.txt", 1), ref("b.txt", 2)])
    assert one.single_source and not two.single_source
