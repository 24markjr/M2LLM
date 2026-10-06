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
    # A difference of two cited figures is derived, not invented (Phase 41): "spend exceeded the
    # approved budget by 37,500" over lines holding 287,500 and 250,000. Differences only - the
    # arithmetic a comparison asks for - and only between figures the claim's own evidence holds.
    derived = {a - b for a in pool_figures for b in pool_figures if a > b}
    for written, value in find_figures(claim):
        if value not in pool_figures and value not in derived:
            missing.append(written)
    return list(dict.fromkeys(missing))


def single_value(claim: str) -> str:
    """The one value a claim states on every side, when it names two or more and they agree.

    Phase 41: asked whether a report contradicts itself, the model wrote "states 30 April 2026 as
    the approved completion date at r10, but also states 30 April 2026 at r15, indicating a single
    date". That is agreement written as a finding. A conflict needs two different values; a claim
    whose dates (or whose figures) are all the same value has none. Returns the value as written,
    or "" when the claim states fewer than two, or different ones.
    """
    dates = find_dates(claim)
    figures = find_figures(claim)
    if len(dates) >= 2 and not figures:
        first = dates[0][1]
        if all(first.compatible(other) for _, other in dates[1:]):
            (start, end), _ = dates[0]
            return claim[start:end]
    if len(figures) >= 2 and not dates and len({value for _, value in figures}) == 1:
        return figures[0][0]
    return ""


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


# Words that name a kind of value rather than what it is about: "dates", "amount", "figure". Sharing
# one of these with a line says nothing about whether the line is about the claim's subject.
_GENERIC = frozenset(
    {
        "date",
        "dates",
        "dated",
        "time",
        "times",
        "day",
        "days",
        "amount",
        "amounts",
        "figure",
        "figures",
        "value",
        "values",
        "number",
        "numbers",
        "state",
        "states",
        "stated",
        "says",
        "said",
        "report",
        "reports",
        "document",
        "documents",
        "record",
        "records",
        "recorded",
        "while",
        "whereas",
        "with",
        "from",
        "that",
        "this",
        "these",
        "those",
        "which",
        "there",
        "their",
        "they",
        "have",
        "been",
        "were",
        "different",
        "differ",
        "differs",
        "both",
        "than",
        "into",
        "over",
        "under",
        "about",
        "also",
        "only",
        "same",
        "other",
        "each",
        "between",
        "january",
        "february",
        "march",
        "april",
        "june",
        "july",
        "august",
        "september",
        "october",
        "november",
        "december",
    }
)
_WORD = re.compile(r"[a-z][a-z'-]{3,}|[a-z]+-?\d+[a-z0-9-]*|\d+-?[a-z]+[a-z0-9-]*", re.IGNORECASE)
# Rows of a table carry their meaning in the column header, not on the row ("migration,450000,no").
_TABULAR = (".csv", ".tsv", ".xlsx", ".xlsm")


def _context_words(text: str) -> set[str]:
    """Content words, cut to six letters so inflections meet ("completed" and "completion" are
    both "comple"); identifiers with digits are kept whole."""
    words = {w.lower().rstrip("'") for w in _WORD.findall(text)} - _GENERIC
    return {w if any(c.isdigit() for c in w) else w[:6] for w in words}


def values_out_of_context(claim: str, evidence: list[EvidenceText]) -> list[str]:
    """Dates and figures that a claim's evidence contains only on lines about something else.

    Found by Phase 41's negative cases, deterministically, in every run:

        claim:    "two different completion dates: 30 April 2026 and 20 April 2026"
        evidence: aurora_project_report.txt:r4  "Date: 20 April 2026"

        claim:    "... the written minutes state it [the handover] as 1 April 2026"
        evidence: orion_minutes.docx:r3  "1. Installation completed on 1 April 2026; ..."

    Both values are on the cited lines, so `ungrounded_specifics` is satisfied - but the first is
    the report's own date and the second the installation date. A value is out of context when every
    cited line holding it shares no word with the claim beyond the value itself: no subject, no
    event, no identifier (`M4`, `PO-7741`). Generic words ("date", "report", month names) do not
    count. Table rows are exempt: their meaning is in the column header, which the row does not
    repeat. Like the rest of this module it reads no meaning; it asks only whether the line is
    about anything the claim is about.
    """
    claim_words = _context_words(claim)
    holders: list[tuple[EvidenceText, set[str]]] = [
        # The locator is not evidence: "aurora_project_report.txt:r4: Date: ..." would otherwise
        # share "aurora" with any claim naming the project.
        (item, _context_words(item.content.removeprefix(f"{item.source}: ")))
        for item in evidence
    ]
    out: list[str] = []

    def lines_with(found: list[EvidenceText]) -> bool:
        return bool(found) and all(
            not item.source.split(":")[0].lower().endswith(_TABULAR) and not (words & claim_words)
            for item, words in holders
            if item in found
        )

    for (start, end), date in find_dates(claim):
        found = [i for i, _ in holders if any(date.compatible(d) for _, d in find_dates(i.content))]
        if lines_with(found):
            out.append(claim[start:end])
    for written, value in find_figures(claim):
        found = [i for i, _ in holders if any(value == v for _, v in find_figures(i.content))]
        if lines_with(found):
            out.append(written)
    return list(dict.fromkeys(out))
