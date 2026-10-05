"""Does every date and figure a claim states appear in the evidence it cites? (Phase 26, A15)

Not part of Member 4's verifier. Added after the Phase 25 audit, when fixing BUG-015 let the model
verifier read real evidence text, and `verification_success` went to 1.000. One of the passes was:

    claim:    "... but the project report states it closes on 28 April 2026"
    evidence: project_report.txt:r10  "The target completion date is 2026-04-30."

The claim's decisive date is in none of the cited text, and the model verifier approved it
(BUG-018).

This check is deterministic and narrow on purpose. It does not judge meaning. It asks only
whether each **specific** in the claim, meaning each date and each figure of three or more digits,
appears somewhere in the evidence. A claim can phrase things freely; it cannot assert a value
nothing it cites contains. Dates match when compatible (`2026-04-30` = `30 April 2026`); figures
match by value (`450,000` = `450000`).
"""

from __future__ import annotations

import re

from app.intelligence.temporal import find_dates, find_figures
from app.schemas.trust import EvidenceText

# A bare number of three or more digits right after a word that introduces a date. "On 2026-04-30"
# does not match (the number runs on into the date), nor do "by driver" and "Shipment 9012".
# "By" and "before" are left out: "delivered by 9012" is more often an agent than a date.
_DATE_POSITION = re.compile(r"\b(?:on|dated|since|until)\s+(\d{3,})\b(?![.,/:-]?\d)", re.IGNORECASE)

# A bare number after "on" can be a year ("on 2026, the budget..."). Outside this range it is not.
_PLAUSIBLE_YEARS = range(1900, 2101)


def ungrounded_specifics(claim: str, evidence: list[EvidenceText]) -> list[str]:
    """The dates and figures in `claim` that no evidence item contains, as the claim wrote them."""
    pool_dates = [date for item in evidence for _, date in find_dates(item.content)]
    pool_figures = {value for item in evidence for _, value in find_figures(item.content)}

    missing: list[str] = []
    for (start, end), date in find_dates(claim):
        if not any(date.compatible(seen) for seen in pool_dates):
            missing.append(claim[start:end])
    for written, value in find_figures(claim):
        if value not in pool_figures:
            missing.append(written)
    return list(dict.fromkeys(missing))


def numbers_as_dates(claim: str) -> list[str]:
    """Numbers a claim puts where a date belongs that cannot be dates (BUG-021).

    "Shipment 9012 was delivered on 9012" took the shipment number for the date. Both verifiers
    passed it, because `9012` does appear on the cited line, so `ungrounded_specifics` is satisfied.
    The value is grounded; its role is not. This asks only the narrow question: does a word that
    introduces a date ("on", "dated", "since", "until") precede a bare number that is no plausible
    year? Like the rest of this module it reads no meaning, so it cannot see a wrong but valid date.
    """
    found = [m.group(1) for m in _DATE_POSITION.finditer(claim)]
    return list(dict.fromkeys(n for n in found if int(n) not in _PLAUSIBLE_YEARS))
