"""Phase 17 — cost-aware action selection.

The policy is a heuristic and the tests treat it as one. They check the *properties* that
make it defensible — cheaper wins at equal value, unscorable actions are dropped, every
score carries its working — rather than asserting specific numbers, which would be testing
the weights rather than the design.
"""

from __future__ import annotations

import pytest

from app.intelligence.evidence_gap.detector import propose_task
from app.intelligence.planning_policy.scoring import (
    ActionScore,
    estimated_cost,
    expected_gain,
    score_action,
    select_actions,
)
from app.schemas.evidence import EvidenceGap, GapType
from app.tools.base import ToolRegistry
from app.tools.builtin import DocumentExtractTool, DocumentSearchTool


def _registry() -> ToolRegistry:
    registry = ToolRegistry()
    registry.register(DocumentSearchTool())
    registry.register(DocumentExtractTool())
    return registry


def _gap(
    gap_type: GapType = GapType.MISSING_SOURCE,
    *,
    severity: float = 0.6,
    query: str = "approved baseline completion date",
    scope: list[str] | None = None,
    gap_id: str = "G-001",
) -> EvidenceGap:
    return EvidenceGap(
        gap_id=gap_id,
        finding_id="F-001",
        gap_type=gap_type,
        missing="the approved baseline completion date",
        severity=severity,
        suggested_query=query,
        suggested_scope=scope or [],
    )


# --- expected information gain -------------------------------------------------


def test_a_missing_baseline_is_worth_more_than_a_stale_source() -> None:
    """A comparison against an unestablished baseline undermines the whole claim."""
    assert expected_gain(_gap(GapType.MISSING_BASELINE)) > expected_gain(_gap(GapType.STALE_SOURCE))


def test_a_specific_query_is_worth_more_than_a_vague_one() -> None:
    specific = expected_gain(_gap(query="approved baseline completion date"))
    vague = expected_gain(_gap(query="budget"))
    assert specific > vague


def test_a_gap_with_no_query_cannot_pay_off() -> None:
    """There is nothing to search for, so the action has no expected value."""
    assert expected_gain(_gap(query="   ")) == 0.0


@pytest.mark.parametrize("gap_type", list(GapType))
def test_every_gap_type_has_a_prior(gap_type: GapType) -> None:
    assert 0.0 <= expected_gain(_gap(gap_type)) <= 1.0


# --- estimated cost ------------------------------------------------------------


def test_a_narrower_scope_costs_less() -> None:
    """A retrieval scoped to two named documents is cheaper than one across twenty."""
    registry = _registry()
    narrow = estimated_cost(propose_task(_gap(scope=["a.txt", "b.txt"]), index=1), registry)
    broad = estimated_cost(propose_task(_gap(), index=1), registry, document_count=20)
    assert narrow < broad


def test_cost_is_always_positive() -> None:
    """Zero cost would make the score infinite and the ranking meaningless."""
    assert estimated_cost(propose_task(_gap(), index=1), _registry()) > 0


def test_a_task_nothing_can_serve_is_made_expensive_rather_than_impossible() -> None:
    """The reason then shows up in the score breakdown instead of vanishing."""
    empty = ToolRegistry()
    assert estimated_cost(propose_task(_gap(), index=1), empty) >= 100.0


# --- scoring -------------------------------------------------------------------


def test_a_higher_severity_gap_scores_higher_at_equal_cost() -> None:
    registry = _registry()
    high = score_action(_gap(severity=0.9), propose_task(_gap(severity=0.9), index=1), registry)
    low = score_action(_gap(severity=0.3), propose_task(_gap(severity=0.3), index=2), registry)
    assert high.score > low.score


def test_the_cheaper_action_wins_at_comparable_value() -> None:
    """The behaviour the phase exists for: prefer the cheap action when it would do."""
    registry = _registry()
    gap = _gap(scope=["a.txt"])
    cheap = score_action(gap, propose_task(gap, index=1), registry, document_count=1)
    expensive = score_action(_gap(), propose_task(_gap(), index=2), registry, document_count=20)
    assert cheap.score > expensive.score


def test_a_score_carries_its_working() -> None:
    """What makes this defensible rather than decorative: it can be argued with."""
    score = score_action(_gap(), propose_task(_gap(), index=1), _registry())

    assert 0.0 <= score.expected_gain <= 1.0
    assert 0.0 <= score.gap_severity <= 1.0
    assert score.estimated_cost > 0
    assert "gain" in score.explain() and "cost" in score.explain()
    assert score.rationale


def test_a_gap_with_no_query_scores_zero() -> None:
    gap = _gap(query="")
    assert score_action(gap, propose_task(gap, index=1), _registry()).score == 0.0


# --- selection -----------------------------------------------------------------


def _score(gap_id: str, value: float) -> ActionScore:
    return ActionScore(
        gap_id=gap_id,
        task_id=f"task_{gap_id[-1]:0>3}",
        score=value,
        expected_gain=0.7,
        gap_severity=0.6,
        estimated_cost=1.0,
    )


def test_selection_is_best_first() -> None:
    selected = select_actions([_score("G-1", 0.2), _score("G-3", 0.9), _score("G-2", 0.5)], limit=3)
    assert [s.gap_id for s in selected] == ["G-3", "G-2", "G-1"]


def test_selection_respects_the_budget() -> None:
    selected = select_actions([_score("G-1", 0.9), _score("G-2", 0.5), _score("G-3", 0.2)], limit=2)
    assert len(selected) == 2
    assert [s.gap_id for s in selected] == ["G-1", "G-2"]


def test_an_unscorable_action_is_dropped_rather_than_executed() -> None:
    """Running it would consume a tool call that cannot pay for itself."""
    selected = select_actions([_score("G-1", 0.0), _score("G-2", 0.4)], limit=5)
    assert [s.gap_id for s in selected] == ["G-2"]


def test_a_zero_budget_selects_nothing() -> None:
    assert select_actions([_score("G-1", 0.9)], limit=0) == []


def test_selection_is_deterministic() -> None:
    scores = [_score("G-1", 0.4), _score("G-2", 0.9), _score("G-3", 0.4)]
    assert [s.gap_id for s in select_actions(scores, limit=3)] == [
        s.gap_id for s in select_actions(scores, limit=3)
    ]


# --- the policy switch ---------------------------------------------------------


def test_the_naive_policy_exists_so_the_heuristic_can_be_measured() -> None:
    """A policy that cannot be switched off cannot be evaluated (Experiment 002)."""
    from app.core.config import PlanningPolicyName

    assert {p.value for p in PlanningPolicyName} == {"heuristic", "naive"}
