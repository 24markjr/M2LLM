"""The timeline: dated claims in order, and the order of any two (K7, K8).

Ported from Member 3's `timeline.py`. Kept: an event is a claim whose attribute contains "date" or
"time"; events are sorted chronologically with unparseable dates last; each is labelled against
the one before it with the original labels (`SAME_TIME_AS`, `AFTER`, `UNKNOWN`); and two claims
compare as `A_BEFORE_B`, `A_AFTER_B`, `SAME_TIME` or `UNKNOWN`.

Changed:

- **No invented year.** The original forced every parsed date to 2026, including dates that stated
  their own year. A missing year stays missing. For **ordering only**, it is inferred as the most
  common explicit year among the run's events, and the event says so (`year_inferred`).
- **A claim whose value is a date is an event even if its attribute name does not say so**
  ("arrived_on"). The original rule missed those.
- **Same time means same granularity.** "April 2026" and "30 April 2026" are compatible but not the
  same time, so their relation is `UNKNOWN` rather than `SAME_TIME_AS`.
- Only grounded claims become events.
"""

from __future__ import annotations

from collections import Counter

from app.intelligence.temporal import compare_dates, parse_date, sort_key
from app.schemas.knowledge import (
    ClaimComparison,
    ClaimOrder,
    KnowledgeClaim,
    KnowledgeEntity,
    TimelineEvent,
    TimelineRelation,
)


def is_dated(claim: KnowledgeClaim) -> bool:
    attribute = claim.attribute.lower()
    return "date" in attribute or "time" in attribute or parse_date(claim.value) is not None


def build_timeline(
    claims: list[KnowledgeClaim],
    entities: list[KnowledgeEntity],
    *,
    entity_id: str | None = None,
) -> list[TimelineEvent]:
    names = {e.entity_id: e.name for e in entities}
    dated = [
        c
        for c in claims
        if c.grounded and is_dated(c) and (entity_id is None or c.entity_id == entity_id)
    ]

    parsed = [(c, parse_date(c.value)) for c in dated]
    years = Counter(d.year for _, d in parsed if d is not None and d.year is not None)
    inferred = years.most_common(1)[0][0] if years else None

    parsed.sort(key=lambda pair: (sort_key(pair[1], inferred), pair[0].claim_id))

    events: list[TimelineEvent] = []
    previous = None
    for index, (claim, date) in enumerate(parsed):
        if index == 0:
            relation = None
        elif date is None or previous is None:
            relation = TimelineRelation.UNKNOWN
        else:
            order = compare_dates(previous, date)
            relation = {
                ClaimOrder.SAME_TIME: TimelineRelation.SAME_TIME_AS,
                ClaimOrder.A_BEFORE_B: TimelineRelation.AFTER,
            }.get(order, TimelineRelation.UNKNOWN)
        events.append(
            TimelineEvent(
                claim_id=claim.claim_id,
                entity_id=claim.entity_id,
                entity_name=names.get(claim.entity_id, claim.entity_id),
                attribute=claim.attribute,
                value=claim.value,
                source=claim.source,
                date=date,
                year_inferred=date is not None and date.year is None and inferred is not None,
                relation_to_previous=relation,
            )
        )
        previous = date
    return events


def compare_claims(a: KnowledgeClaim, b: KnowledgeClaim) -> ClaimComparison:
    date_a, date_b = parse_date(a.value), parse_date(b.value)
    if date_a is None or date_b is None:
        return ClaimComparison(
            claim_a=a,
            claim_b=b,
            date_a=date_a,
            date_b=date_b,
            relation=ClaimOrder.UNKNOWN,
            reason="could not parse a date from one or both claims",
        )
    relation = compare_dates(date_a, date_b)
    reason = (
        "the dates are compatible but stated at different precision"
        if relation is ClaimOrder.UNKNOWN
        else ""
    )
    return ClaimComparison(
        claim_a=a, claim_b=b, date_a=date_a, date_b=date_b, relation=relation, reason=reason
    )
