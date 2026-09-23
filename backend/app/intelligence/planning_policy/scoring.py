"""Cost-aware action selection.

When several actions could close a gap, spend the budget on the one that buys the most
certainty per unit of work:

    score = (expected_information_gain * gap_severity) / (estimated_cost + epsilon)

**This is a heuristic and is presented as one.** The priors below are judgements about which
kinds of missing evidence tend to matter, not measured quantities. Precision here would be
false precision: we do not know a retrieval's information gain before performing it, and
pretending otherwise would dress a guess as a calculation.

What makes it defensible rather than decorative is that every score is **recorded with its
breakdown**. A selection can be inspected, argued with, and — through the `naive` policy —
measured against not doing it at all. Phase 20's Experiment 002 runs exactly that comparison:
tasks executed per resolved finding, with the policy on and off. If coverage drops when the
policy is on, it is trading correctness for cost and these weights are wrong.
"""

from __future__ import annotations

from pydantic import Field

from app.core.logging import get_logger
from app.schemas.common import CostHint, JarvisModel, UnitFloat
from app.schemas.evidence import EvidenceGap, GapType
from app.schemas.task import Task
from app.tools.base import ToolRegistry

log = get_logger(__name__)

EPSILON = 0.1

# How much resolving each kind of gap tends to be worth. A missing baseline scores highest
# because a comparison against an unestablished baseline undermines the entire claim, not
# merely one element of it.
_GAIN_PRIOR: dict[GapType, float] = {
    GapType.MISSING_BASELINE: 0.9,
    GapType.CONFLICTING_SOURCES: 0.8,
    GapType.MISSING_SOURCE: 0.7,
    GapType.UNRESOLVED_CITATION: 0.6,
    GapType.INSUFFICIENT_GRANULARITY: 0.5,
    GapType.STALE_SOURCE: 0.4,
}

_COST_WEIGHT: dict[CostHint, float] = {
    CostHint.LOW: 1.0,
    CostHint.MEDIUM: 3.0,
    CostHint.HIGH: 10.0,
}


class ActionScore(JarvisModel):
    """A scored candidate action, carrying the working that produced the number."""

    gap_id: str
    task_id: str
    score: float = Field(ge=0.0)
    expected_gain: UnitFloat
    gap_severity: UnitFloat
    estimated_cost: float = Field(gt=0.0)
    rationale: str = ""

    def explain(self) -> str:
        return (
            f"{self.score:.2f} = (gain {self.expected_gain:.2f} "
            f"x severity {self.gap_severity:.2f}) / cost {self.estimated_cost:.2f}"
        )


def expected_gain(gap: EvidenceGap) -> float:
    """How much resolving this gap is expected to be worth.

    A gap with a specific, narrow query scores higher than a vague one: a query naming a
    particular element is more likely to retrieve something that actually resolves it.
    """
    prior = _GAIN_PRIOR.get(gap.gap_type, 0.5)
    query = gap.suggested_query.strip()

    if not query:
        # Nothing to search for. The action cannot pay off at all.
        return 0.0

    # A very short query is usually too broad to resolve a named element.
    specificity = 1.0 if len(query.split()) >= 3 else 0.8
    return min(1.0, prior * specificity)


def estimated_cost(task: Task, registry: ToolRegistry, *, document_count: int = 1) -> float:
    """What this action is likely to cost, in arbitrary but consistent units.

    Derived from the cheapest tool that could serve the task and how much material it would
    have to read. A retrieval scoped to two named documents costs less than an unscoped one
    across twenty.
    """
    candidates = registry.serving(task.required_capability)
    if not candidates:
        # Nothing can run it; make it unattractive rather than impossible, so the reason
        # shows up in the score breakdown rather than vanishing.
        return 100.0

    cheapest = min(candidates, key=lambda t: _COST_WEIGHT[t.cost_hint])
    base = _COST_WEIGHT[cheapest.cost_hint]

    scope = task.inputs.get("scope")
    breadth = len(scope) if isinstance(scope, list) and scope else max(document_count, 1)

    return base * (1.0 + 0.2 * (breadth - 1))


def score_action(
    gap: EvidenceGap,
    task: Task,
    registry: ToolRegistry,
    *,
    document_count: int = 1,
) -> ActionScore:
    """Score one candidate action, keeping the working."""
    gain = expected_gain(gap)
    cost = estimated_cost(task, registry, document_count=document_count)
    score = (gain * gap.severity) / (cost + EPSILON)

    return ActionScore(
        gap_id=gap.gap_id,
        task_id=task.task_id,
        score=score,
        expected_gain=gain,
        gap_severity=gap.severity,
        estimated_cost=cost,
        rationale=(
            f"{gap.gap_type.value} scoped to "
            f"{len(task.inputs.get('scope') or []) or document_count} document(s)"
        ),
    )


def select_actions(
    scored: list[ActionScore],
    *,
    limit: int,
    min_score: float = 0.0,
) -> list[ActionScore]:
    """Pick the actions worth spending the remaining budget on.

    Best-first, capped by the budget. An action scoring zero — a gap with no query, or one
    nothing can serve — is dropped rather than executed, because running it would consume a
    tool call that cannot pay for itself.
    """
    viable = [s for s in scored if s.score > min_score]
    viable.sort(key=lambda s: s.score, reverse=True)
    selected = viable[: max(limit, 0)]

    for action in selected:
        log.info("action_selected", gap_id=action.gap_id, score=round(action.score, 3))
    dropped = len(scored) - len(selected)
    if dropped:
        log.info("actions_dropped", count=dropped, reason="below budget or unscorable")

    return selected
