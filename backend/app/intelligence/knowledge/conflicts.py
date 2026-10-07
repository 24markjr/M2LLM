"""Contradiction detection across claims (K6).

Ported from Member 3's `contradictions.py`. The rule is the original's:

1. Deduplicate identical claims (same entity, attribute, value and source).
2. Group by (entity, attribute).
3. A group with more than one distinct value is a conflict, reported with every side's citations.
4. **Never decide which side is right.** Judging it is the reasoning engine's and the
   verifier's job.

What changed is what "distinct" means. The original compared lower-cased strings, so "30 April
2026" and "2026-04-30" conflicted, and so did "INR 380,000" and "380000". Values now compare by
kind:

- `DATE`, when every value parses as a date: the same if compatible (no field known on both
  sides differs).
- `NUMBER`, when every value is a single number: the same if numerically equal.
- `TEXT`, otherwise: the same if equal after case and whitespace folding.

And one addition: **only grounded claims take part.** A value the model wrote rather than read
from its cited line cannot be one side of a contradiction.

**Not every difference is a contradiction (BUG-033, 2026-10-07).** On twelve AURORA project
documents, all six "conflicts" were one document describing the system in other words on different
pages: "description = Automated Unified Reasoning and Optimization Architecture" against "Automated
Compliance Validation". Both are true; nothing contradicts. So disagreements are now split:

- **Contradictions** (`conflicts`): dates and numbers that differ; and text only when every value is
  short and categorical (a name, a status - four words at most) *and* the sides come from different
  documents ("on duty: Arjun Verma" against "Rahul Sharma").
- **Differing descriptions** (`differences`): any other text difference. Kept, shown, never red.

A date or number contradiction within one document stays a contradiction and is marked
`same_document`, because a document can give a planned and an actual date for one thing.
"""

from __future__ import annotations

import re
from collections.abc import Callable
from decimal import Decimal

from app.intelligence.temporal import parse_date, parse_number
from app.schemas.knowledge import (
    ClaimConflict,
    ConflictKind,
    ConflictSide,
    KnowledgeClaim,
    KnowledgeEntity,
    PartialDate,
)


def _fold(value: str) -> str:
    return " ".join(value.casefold().split())


# "Q2 2026", "Q2-2026", "2026 Q2", "Q2 FY2026": a quarter is a date range, not text. Without this,
# "production readiness in Q2 2026" against "closed 14 May 2026" was reported as a contradiction
# (found by Step 1's live check on the Aurora reports) - and 14 May is in Q2.
_QUARTER = re.compile(
    r"^\s*(?:Q([1-4])[\s-]*(?:FY\s*)?(\d{4})|(\d{4})[\s-]*Q([1-4]))\s*$", re.IGNORECASE
)


def _quarter(value: str) -> tuple[int, range] | None:
    match = _QUARTER.match(value)
    if match is None:
        return None
    quarter = int(match.group(1) or match.group(4))
    year = int(match.group(2) or match.group(3))
    return year, range(3 * quarter - 2, 3 * quarter + 1)


def _dateish(value: str) -> bool:
    return parse_date(value) is not None or _quarter(value) is not None


def _kind(values: list[str]) -> ConflictKind:
    if all(_dateish(v) for v in values):
        return ConflictKind.DATE
    if all(parse_number(v) is not None for v in values):
        return ConflictKind.NUMBER
    return ConflictKind.TEXT


def _same(kind: ConflictKind) -> Callable[[str, str], bool]:
    if kind is ConflictKind.DATE:

        def same_date(a: str, b: str) -> bool:
            qa, qb = _quarter(a), _quarter(b)
            if qa is not None or qb is not None:
                return _same_period(a, qa, b, qb)
            first, second = parse_date(a), parse_date(b)
            return (
                isinstance(first, PartialDate)
                and isinstance(second, PartialDate)
                and (first.compatible(second))
            )

        return same_date
    if kind is ConflictKind.NUMBER:

        def same_number(a: str, b: str) -> bool:
            first, second = parse_number(a), parse_number(b)
            return isinstance(first, Decimal) and first == second

        return same_number
    return lambda a, b: _fold(a) == _fold(b)


# A text value of at most this many words is categorical (a name, a status, a yes/no); longer text
# is a description, and two descriptions differing in wording do not contradict each other.
CATEGORICAL_WORDS = 4


def _document(source: str) -> str:
    return source.rsplit(":", 1)[0] if ":" in source else source


def is_contradiction(conflict: ClaimConflict) -> bool:
    """Whether a disagreement contradicts, or only describes the same thing differently."""
    if conflict.kind is not ConflictKind.TEXT:
        return True
    categorical = all(len(side.value.split()) <= CATEGORICAL_WORDS for side in conflict.sides)
    return categorical and not conflict.same_document


def _same_period(
    a: str, qa: tuple[int, range] | None, b: str, qb: tuple[int, range] | None
) -> bool:
    """A quarter matches the same quarter, or any date that falls inside it."""
    if qa is not None and qb is not None:
        return qa == qb
    quarter, other = (qa, b) if qa is not None else (qb, a)
    assert quarter is not None
    date = parse_date(other)
    if not isinstance(date, PartialDate):
        return False
    year, months = quarter
    return (date.year is None or date.year == year) and date.month in months


def detect_conflicts(
    claims: list[KnowledgeClaim], entities: list[KnowledgeEntity]
) -> list[ClaimConflict]:
    """The contradictions among `claims` (differing descriptions left out)."""
    return detect_disagreements(claims, entities)[0]


def detect_disagreements(
    claims: list[KnowledgeClaim], entities: list[KnowledgeEntity]
) -> tuple[list[ClaimConflict], list[ClaimConflict]]:
    """Every disagreement, split into (contradictions, differing descriptions)."""
    names = {e.entity_id: e.name for e in entities}

    # 1. Deduplicate, and drop what the model wrote rather than read.
    seen: set[tuple[str, str, str, str]] = set()
    unique: list[KnowledgeClaim] = []
    for claim in claims:
        if not claim.grounded:
            continue
        key = (claim.entity_id, claim.attribute, _fold(claim.value), claim.source)
        if key not in seen:
            seen.add(key)
            unique.append(claim)

    # 2. Group by (entity, attribute), keeping first-seen order so results are reproducible.
    groups: dict[tuple[str, str], list[KnowledgeClaim]] = {}
    for claim in unique:
        groups.setdefault((claim.entity_id, claim.attribute), []).append(claim)

    # 3. Cluster each group's values; more than one cluster is a disagreement.
    conflicts: list[ClaimConflict] = []
    differences: list[ClaimConflict] = []
    for (entity_id, attribute), group in groups.items():
        kind = _kind([c.value for c in group])
        same = _same(kind)
        clusters: list[list[KnowledgeClaim]] = []
        for claim in group:
            for cluster in clusters:
                if same(cluster[0].value, claim.value):
                    cluster.append(claim)
                    break
            else:
                clusters.append([claim])
        if len(clusters) < 2:
            continue

        sides = [
            ConflictSide(
                value=cluster[0].value,
                claim_ids=[c.claim_id for c in cluster],
                sources=list(dict.fromkeys(c.source for c in cluster)),
            )
            for cluster in clusters
        ]
        disagreement = ClaimConflict(
            conflict_id="CON-000",
            entity_id=entity_id,
            entity_name=names.get(entity_id, entity_id),
            attribute=attribute,
            kind=kind,
            sides=sides,
            same_document=len({_document(s) for side in sides for s in side.sources}) == 1,
        )
        if is_contradiction(disagreement):
            conflicts.append(
                disagreement.model_copy(update={"conflict_id": f"CON-{len(conflicts) + 1:03d}"})
            )
        else:
            differences.append(
                disagreement.model_copy(update={"conflict_id": f"DIF-{len(differences) + 1:03d}"})
            )
    return conflicts, differences
