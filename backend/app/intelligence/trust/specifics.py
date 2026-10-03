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

from app.intelligence.temporal import find_dates, find_figures
from app.schemas.trust import EvidenceText


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
