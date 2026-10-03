"""Dates, times and numbers as sources write them, shared by the knowledge layer and the verifier.

Both teammates parsed time on their own, differently, and each version had a defect the other
did not:

- Member 3 (`timeline.py`) tried six `strptime` formats and then **forced every date to 2026**,
  including dates that stated their own year.
- Member 4 (`trust/verifier.py`) compared clock times as lower-cased strings with spaces
  removed, so `11:40` and `11:40 AM` were different times and counted as a conflict. It could
  not see dates at all, so a wrong date was never a contradiction.

One parser serves both now. It recognises the original six date formats, adds month abbreviations
and month-plus-year, never invents a year, and compares times by the minute they denote.
"""

from __future__ import annotations

import re
from calendar import monthrange
from decimal import Decimal, InvalidOperation

from app.schemas.knowledge import ClaimOrder, PartialDate

_MONTHS: dict[str, int] = {}
for _number, _names in enumerate(
    [
        ("january", "jan"),
        ("february", "feb"),
        ("march", "mar"),
        ("april", "apr"),
        ("may",),
        ("june", "jun"),
        ("july", "jul"),
        ("august", "aug"),
        ("september", "sep", "sept"),
        ("october", "oct"),
        ("november", "nov"),
        ("december", "dec"),
    ],
    start=1,
):
    for _name in _names:
        _MONTHS[_name] = _number

_MONTH = r"(?P<month>" + "|".join(sorted(_MONTHS, key=len, reverse=True)) + r")\.?"
_ORDINAL = r"(?:st|nd|rd|th)?"

# Tried in this order. An earlier pattern wins where two overlap, which is what lets
# "14 September 2026" be read once as a full date rather than also as "September 2026".
_DATE_PATTERNS: tuple[re.Pattern[str], ...] = (
    # 2026-04-30
    re.compile(r"\b(?P<year>\d{4})-(?P<month_n>\d{1,2})-(?P<day>\d{1,2})\b"),
    # 14 September, 14 September 2026, 14th Sept. 2026   (original: %d %B, %d %B %Y)
    re.compile(
        rf"\b(?P<day>\d{{1,2}}){_ORDINAL}\s+{_MONTH},?(?:\s+(?P<year>\d{{4}}))?\b", re.IGNORECASE
    ),
    # September 14, September 14, 2026   (original: %B %d, %B %d, %Y)
    re.compile(
        rf"\b{_MONTH}\s+(?P<day>\d{{1,2}}){_ORDINAL}(?:,?\s+(?P<year>\d{{4}}))?\b", re.IGNORECASE
    ),
    # 30/04/2026, 30-04-2026 - day first   (original: %d/%m/%Y, %d-%m-%Y)
    re.compile(r"\b(?P<day>\d{1,2})[/-](?P<month_n>\d{1,2})[/-](?P<year>\d{4})\b"),
    # April 2026 - month and year, no day. New: a schedule often says only this.
    re.compile(rf"\b{_MONTH}\s+(?P<year>\d{{4}})\b", re.IGNORECASE),
)

# Member 4's time pattern, unchanged: `\b\d{1,2}:\d{2}\s*(?:am|pm)?\b`, with the groups named.
_TIME = re.compile(
    r"\b(?P<hour>\d{1,2}):(?P<minute>\d{2})\s*(?P<meridiem>am|pm|a\.m\.|p\.m\.)?(?![\w])",
    re.IGNORECASE,
)

# Member 4's identifying-number pattern, unchanged: standalone numbers of three or more digits.
_ID = re.compile(r"\b\d{3,}\b")

_NUMBER = re.compile(r"-?\d[\d,]*(?:\.\d+)?")
_CURRENCY_WORDS = re.compile(
    r"\b(?:inr|usd|eur|gbp|rs\.?|rupees?|dollars?|euros?)\b|[$£€₹]", re.IGNORECASE
)


def find_dates(text: str) -> list[tuple[tuple[int, int], PartialDate]]:
    """Every date in `text`, with its character span, in order of appearance."""
    taken: list[tuple[int, int]] = []
    found: list[tuple[tuple[int, int], PartialDate]] = []

    for pattern in _DATE_PATTERNS:
        for match in pattern.finditer(text):
            span = match.span()
            if any(span[0] < end and start < span[1] for start, end in taken):
                continue
            date = _from_match(match)
            if date is None:
                continue
            taken.append(span)
            found.append((span, date))

    found.sort(key=lambda item: item[0][0])
    return found


def parse_date(value: str) -> PartialDate | None:
    """The first date in a value such as "14 September" or "on 30 April 2026", or None.

    The original required the whole value to match one format. Extraction routinely returns
    "on 14 September" or "14 September (revised)", which that rejected.
    """
    dates = find_dates(value)
    return dates[0][1] if dates else None


def _from_match(match: re.Match[str]) -> PartialDate | None:
    groups = match.groupdict()
    if groups.get("month_n"):
        month = int(groups["month_n"])
    else:
        month = _MONTHS.get((groups.get("month") or "").lower().rstrip("."), 0)
    year = int(groups["year"]) if groups.get("year") else None
    day = int(groups["day"]) if groups.get("day") else None

    if not 1 <= month <= 12:
        return None
    if day is not None:
        # Check against a leap year when the year is unknown, so 29 February is allowed.
        if not 1 <= day <= monthrange(year or 2000, month)[1]:
            return None
    if year is not None and not 1000 <= year <= 9999:
        return None
    return PartialDate(year=year, month=month, day=day)


def compare_dates(a: PartialDate, b: PartialDate) -> ClaimOrder:
    """Order two dates, or say they cannot be ordered.

    Equal only at the same granularity: "April 2026" and "30 April 2026" are compatible, but
    calling them the same time would claim a precision neither source gave.
    """
    if a.year is not None and b.year is not None and a.year != b.year:
        return ClaimOrder.A_BEFORE_B if a.year < b.year else ClaimOrder.A_AFTER_B
    if a.month != b.month:
        return ClaimOrder.A_BEFORE_B if a.month < b.month else ClaimOrder.A_AFTER_B
    if a.day is not None and b.day is not None and a.day != b.day:
        return ClaimOrder.A_BEFORE_B if a.day < b.day else ClaimOrder.A_AFTER_B
    if a.granularity == b.granularity and a == b:
        return ClaimOrder.SAME_TIME
    return ClaimOrder.UNKNOWN


def sort_key(date: PartialDate | None, inferred_year: int | None) -> tuple[int, int, int, int]:
    """Chronological sort key. Unparsed dates sort last, as the original's "9999" did."""
    if date is None:
        return (1, 9999, 13, 32)
    year = date.year if date.year is not None else (inferred_year or 0)
    return (0, year, date.month, date.day or 0)


# --- times ----------------------------------------------------------------------


def find_times(text: str) -> list[tuple[int, int, bool]]:
    """Clock times as (hour, minute, has_meridiem), with am/pm folded into a 24-hour hour."""
    found: list[tuple[int, int, bool]] = []
    for match in _TIME.finditer(text):
        hour, minute = int(match.group("hour")), int(match.group("minute"))
        if hour > 23 or minute > 59:
            continue
        meridiem = (match.group("meridiem") or "").lower().replace(".", "")
        if meridiem == "pm" and hour < 12:
            hour += 12
        elif meridiem == "am" and hour == 12:
            hour = 0
        found.append((hour, minute, bool(meridiem)))
    return found


def same_time(a: tuple[int, int, bool], b: tuple[int, int, bool]) -> bool:
    """Whether two clock times can denote the same minute.

    When one side gives no am/pm, `11:40` is compatible with both `11:40 AM` and `11:40 PM`.
    The original compared strings, so `11:40` against `11:40 AM` counted as a conflict.
    """
    if a[1] != b[1]:
        return False
    if a[2] and b[2]:
        return a[0] == b[0]
    return a[0] % 12 == b[0] % 12


def times_disjoint(a: list[tuple[int, int, bool]], b: list[tuple[int, int, bool]]) -> bool:
    """Both sides name times and no time on one side can match a time on the other."""
    return bool(a) and bool(b) and not any(same_time(x, y) for x in a for y in b)


def dates_disjoint(a: list[PartialDate], b: list[PartialDate]) -> bool:
    """Both sides name dates and no date on one side is compatible with a date on the other."""
    return bool(a) and bool(b) and not any(x.compatible(y) for x in a for y in b)


# --- identifiers and numbers ----------------------------------------------------


def identifiers(text: str) -> set[str]:
    """Member 4's identifying numbers (3+ digits), **excluding digits inside a date**.

    The original read the year in "30 April 2026" as an identifier. Two unrelated statements
    about different 2026 events then "shared an ID" and became eligible to contradict each other.
    """
    masked = text
    for (start, end), _ in reversed(find_dates(text)):
        masked = masked[:start] + " " * (end - start) + masked[end:]
    return set(_ID.findall(masked))


def parse_number(value: str) -> Decimal | None:
    """A single number in a value such as "INR 380,000" or "$1,200.50", or None.

    Only when the value is essentially one number. "Phase 2 of 3" is not a number, and reading
    it as 2 would make two phases look like a numeric conflict.
    """
    stripped = _CURRENCY_WORDS.sub(" ", value).strip()
    matches = _NUMBER.findall(stripped)
    if len(matches) != 1:
        return None
    if len(stripped.replace(matches[0], "").strip(" .,")) > 0:
        return None
    try:
        return Decimal(matches[0].replace(",", ""))
    except InvalidOperation:
        return None
