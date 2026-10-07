"""BUG-033: not every difference between claims is a contradiction.

Built from a real run (run_9b03bd99041a, twelve AURORA project documents, 2026-10-07): all six of
its "conflicts" were one document describing the system in other words on different pages. Each of
those six is here and must be a differing description, while the contradictions the evaluation
scenarios depend on must stay contradictions.
"""

from __future__ import annotations

import pytest

from app.intelligence.knowledge.base import InMemoryKnowledgeBase
from app.intelligence.knowledge.conflicts import detect_conflicts, detect_disagreements
from app.intelligence.knowledge.view import build_view
from app.schemas.knowledge import (
    ConflictKind,
    GraphLinkKind,
    KnowledgeClaim,
    KnowledgeEntity,
    KnowledgeSnapshot,
)

ANNEX = "AURORA_Annexure-1_PS-71.pdf"


def _claim(
    n: int, attribute: str, value: str, source: str, entity: str = "ENT-1"
) -> KnowledgeClaim:
    return KnowledgeClaim(
        claim_id=f"CLM-{n:03d}",
        entity_id=entity,
        attribute=attribute,
        value=value,
        source=source,
        document_id=source.rsplit(":", 1)[0],
        line=1,
    )


ENTITIES = [KnowledgeEntity(entity_id="ENT-1", name="AURORA")]

# The six "conflicts" of run_9b03bd99041a, verbatim: one document, other words.
FALSE_CONFLICTS = [
    (
        "description",
        "Automated Unified Reasoning and Optimization Architecture",
        f"{ANNEX}:p1",
        "Automated Compliance Validation",
        f"{ANNEX}:p2",
    ),
    (
        "problem_addressed",
        "Design Optimization, Compliance Validation, and CAD-BOM Synchronization",
        f"{ANNEX}:p2",
        "CAD-BOM matching model",
        f"{ANNEX}:p6",
    ),
    (
        "synchronization_method",
        "continuously reconciles CAD assemblies with BOM records",
        f"{ANNEX}:p2",
        "CAD-BOM Sync",
        f"{ANNEX}:p8",
    ),
    (
        "consistency_ensured",
        "ensuring data consistency across the lifecycle",
        f"{ANNEX}:p2",
        "end-to-end pipeline integration",
        f"{ANNEX}:p6",
    ),
    (
        "function",
        "Automated Compliance Validation",
        f"{ANNEX}:p2",
        "Automated Unified Reasoning and Optimization Architecture",
        f"{ANNEX}:p8",
    ),
    (
        "design_modifications",
        "4 historical scenarios",
        f"{ANNEX}:p6",
        "impact propagation",
        f"{ANNEX}:p9",
    ),
]


@pytest.mark.parametrize(("attribute", "first", "where", "second", "where_else"), FALSE_CONFLICTS)
def test_one_document_in_other_words_is_a_differing_description(
    attribute: str, first: str, where: str, second: str, where_else: str
) -> None:
    claims = [_claim(1, attribute, first, where), _claim(2, attribute, second, where_else)]
    contradictions, differences = detect_disagreements(claims, ENTITIES)
    assert contradictions == []
    [difference] = differences
    assert difference.conflict_id == "DIF-001" and difference.same_document


@pytest.mark.parametrize(
    ("attribute", "first", "where", "second", "where_else", "kind"),
    [
        # The Aurora scenario: two documents, two completion dates.
        (
            "completion_date",
            "30 April 2026",
            "project.txt:r10",
            "14 May 2026",
            "finance.txt:r12",
            ConflictKind.DATE,
        ),
        # Helix: the budget against the spend recorded.
        (
            "budget",
            "380,000",
            "project_report.txt:r15",
            "450,000",
            "budget.csv:r2",
            ConflictKind.NUMBER,
        ),
        # Member 3's shipment: who was on duty, short categorical values across two statements.
        (
            "manager_on_duty",
            "Arjun Verma",
            "witness.txt:r1",
            "Rahul Sharma",
            "report_a.txt:r1",
            ConflictKind.TEXT,
        ),
    ],
)
def test_real_contradictions_stay_contradictions(
    attribute: str, first: str, where: str, second: str, where_else: str, kind: ConflictKind
) -> None:
    claims = [_claim(1, attribute, first, where), _claim(2, attribute, second, where_else)]
    contradictions, differences = detect_disagreements(claims, ENTITIES)
    [contradiction] = contradictions
    assert contradiction.kind is kind and not contradiction.same_document and differences == []


def test_a_date_contradiction_inside_one_document_is_kept_and_marked() -> None:
    """A document can give a planned and an actual date: still a contradiction, but said to be
    from one source, so a reader checks the context."""
    claims = [
        _claim(1, "completion_date", "30 April 2026", "report.txt:r10"),
        _claim(2, "completion_date", "14 May 2026", "report.txt:r40"),
    ]
    [contradiction] = detect_conflicts(claims, ENTITIES)
    assert contradiction.same_document


def test_a_short_text_difference_within_one_document_is_only_a_description() -> None:
    claims = [
        _claim(1, "status", "approved", "memo.txt:r2"),
        _claim(2, "status", "pending", "memo.txt:r9"),
    ]
    contradictions, differences = detect_disagreements(claims, ENTITIES)
    assert contradictions == [] and len(differences) == 1


async def test_the_graph_draws_differences_apart_from_contradictions() -> None:
    claims = [
        _claim(1, "description", FALSE_CONFLICTS[0][1], FALSE_CONFLICTS[0][2]),
        _claim(2, "description", FALSE_CONFLICTS[0][3], FALSE_CONFLICTS[0][4]),
        _claim(3, "completion_date", "30 April 2026", "project.txt:r10"),
        _claim(4, "completion_date", "14 May 2026", "finance.txt:r12"),
    ]
    contradictions, differences = detect_disagreements(claims, ENTITIES)
    base = InMemoryKnowledgeBase(
        KnowledgeSnapshot(
            entities=ENTITIES, claims=claims, conflicts=contradictions, differences=differences
        )
    )
    view = await build_view(base, "run_x", [])
    kinds = {(link.source, link.target): link.kind for link in view.links}
    assert kinds[("CLM-003", "CLM-004")] is GraphLinkKind.CONFLICTS_WITH
    assert kinds[("CLM-001", "CLM-002")] is GraphLinkKind.DIFFERS_FROM
    assert len(await base.conflicts()) == 1 and len(await base.differences()) == 1


def test_knowledge_stored_before_the_split_still_parses() -> None:
    old = KnowledgeSnapshot.model_validate({"entities": [], "claims": [], "conflicts": []})
    assert old.differences == []


@pytest.mark.parametrize(
    ("quarter", "date", "contradicts"),
    [
        ("Q2 2026", "14 May 2026", False),  # the Aurora reports: inside the quarter
        ("2026 Q2", "30 June 2026", False),
        ("Q2-2026", "Q2 2026", False),
        ("Q2 2026", "14 August 2026", True),
        ("Q1 FY2026", "14 May 2026", True),
    ],
)
def test_a_quarter_is_a_period_not_text(quarter: str, date: str, contradicts: bool) -> None:
    """Found by Step 1's live check: "production readiness Q2 2026" against "closed 14 May 2026"
    was reported as a contradiction."""
    claims = [
        _claim(1, "production_readiness_date", quarter, "project.txt:r7"),
        _claim(2, "production_readiness_date", date, "milestones.txt:r7"),
    ]
    contradictions, differences = detect_disagreements(claims, ENTITIES)
    assert bool(contradictions) is contradicts and differences == []
    if contradicts:
        assert contradictions[0].kind is ConflictKind.DATE
