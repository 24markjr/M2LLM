"""Whether a claim's dates are in the order it says they are - checked by code, never by the model.

Measured on the VAJRA demonstration case (2026-10-30): the model wrote "Payment was released on
25 March 2026, which is after the inspection report was issued on 2 April 2026", and the verifier
passed it - both dates were on the cited lines, so the claim looked grounded. The order of two
dates is arithmetic, like a total (`arithmetic.py`), and is checked the same way: by code.

A claim is checked when it names exactly two full dates (day and month; a missing year is taken
from the other date) and one ordering word between them - after, later than, following, before,
prior to, earlier than, ahead of. Anything else - one date, three, a negation, an ordering word
elsewhere - is left to the verifier, never guessed at.
"""

from __future__ import annotations

import re
from datetime import date

from app.intelligence.temporal import find_dates
from app.schemas.common import JarvisModel
from app.schemas.knowledge import PartialDate

_AFTER = re.compile(r"\b(after|later than|following|subsequent to)\b", re.IGNORECASE)
_BEFORE = re.compile(r"\b(before|prior to|earlier than|ahead of|preceding)\b", re.IGNORECASE)
_NEGATED = re.compile(r"\b(not|n't|never|no)\b[\w\s,]{0,12}$", re.IGNORECASE)


class ChronologyCheck(JarvisModel):
    checked: bool = False
    holds: bool = True
    reason: str = ""


def _as_date(value: PartialDate, year: int | None) -> date | None:
    known_year = value.year if value.year is not None else year
    if known_year is None or value.day is None:
        return None
    try:
        return date(known_year, value.month, value.day)
    except ValueError:
        return None


def check_chronology(claim: str) -> ChronologyCheck:
    found = find_dates(claim)
    if len(found) != 2:
        return ChronologyCheck()
    (span_a, first), (span_b, second) = found
    between = claim[span_a[1] : span_b[0]]
    after, before = _AFTER.findall(between), _BEFORE.findall(between)
    if len(after) + len(before) != 1:
        return ChronologyCheck()
    word_at = (_AFTER.search(between) or _BEFORE.search(between)).start()  # type: ignore[union-attr]
    if _NEGATED.search(between[:word_at]):
        return ChronologyCheck()
    a = _as_date(first, second.year)
    b = _as_date(second, first.year)
    if a is None or b is None or a == b:
        return ChronologyCheck()
    says_after = bool(after)
    holds = a > b if says_after else a < b
    written_a = claim[span_a[0] : span_a[1]]
    written_b = claim[span_b[0] : span_b[1]]
    relation = "after" if says_after else "before"
    if holds:
        return ChronologyCheck(checked=True, reason=f"{written_a} is {relation} {written_b}")
    actual = "before" if says_after else "after"
    return ChronologyCheck(
        checked=True,
        holds=False,
        reason=(
            f"the claim says {written_a} is {relation} {written_b}, but {written_a} is {actual} "
            f"{written_b}"
        ),
    )
