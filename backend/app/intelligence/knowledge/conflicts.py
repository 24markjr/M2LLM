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
"""

from __future__ import annotations

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


def _kind(values: list[str]) -> ConflictKind:
    if all(parse_date(v) is not None for v in values):
        return ConflictKind.DATE
    if all(parse_number(v) is not None for v in values):
        return ConflictKind.NUMBER
    return ConflictKind.TEXT


def _same(kind: ConflictKind) -> Callable[[str, str], bool]:
    if kind is ConflictKind.DATE:

        def same_date(a: str, b: str) -> bool:
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


def detect_conflicts(
    claims: list[KnowledgeClaim], entities: list[KnowledgeEntity]
) -> list[ClaimConflict]:
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

    # 3. Cluster each group's values; more than one cluster is a conflict.
    conflicts: list[ClaimConflict] = []
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

        conflicts.append(
            ClaimConflict(
                conflict_id=f"CON-{len(conflicts) + 1:03d}",
                entity_id=entity_id,
                entity_name=names.get(entity_id, entity_id),
                attribute=attribute,
                kind=kind,
                sides=[
                    ConflictSide(
                        value=cluster[0].value,
                        claim_ids=[c.claim_id for c in cluster],
                        sources=list(dict.fromkeys(c.source for c in cluster)),
                    )
                    for cluster in clusters
                ],
            )
        )
    return conflicts
