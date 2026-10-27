"""Totals and differences are computed by code, not taken from the model (v4 Phase 2).

A small model writes "an overrun of 37,500" as readily as "an overrun of 47,500". Verification asks
whether the cited lines support each figure, and a computed figure is on no line, so a wrong one was
reported as merely unsupported - or, worse, the lexical checker found its digits elsewhere. Here the
arithmetic a claim states is redone from the claim's own figures:

- a claim about a **difference** (exceeds, overrun, short by, more than, variance...) with three or
  more figures holds when one of them is the difference of two others;
- a claim about a **total** (total, sum, combined, altogether) holds when one figure is the sum of
  the others.

When neither holds, the arithmetic is wrong and confidence takes a penalty that says what the
figures actually give. Claims with fewer than three figures state no arithmetic to redo.
"""

from __future__ import annotations

import re
from decimal import Decimal
from itertools import combinations, permutations

from app.intelligence.temporal import find_figures
from app.schemas.common import JarvisModel

_DIFFERENCE = re.compile(
    r"\b(exceed\w*|overrun|over by|over budget|short\w*|shortfall|difference|differ\w*|more than|"
    r"less than|higher|lower|increase\w*|decrease\w*|variance|gap|above|below|excess|deficit|"
    r"overpa\w*|underpa\w*)\b",
    re.IGNORECASE,
)
_TOTAL = re.compile(r"\b(total\w*|sum|combined|altogether|in all|aggregate)\b", re.IGNORECASE)

# Rounding a writer may do ("an overrun of about 37,500"): half a percent of the larger figure.
_TOLERANCE = Decimal("0.005")


class ArithmeticCheck(JarvisModel):
    checked: bool = False
    holds: bool = True
    reason: str = "the claim states no difference or total to recompute"


def _close(a: Decimal, b: Decimal) -> bool:
    return abs(a - b) <= _TOLERANCE * max(abs(a), abs(b), Decimal(1))


def check_arithmetic(claim: str) -> ArithmeticCheck:
    figures = find_figures(claim)
    values = [v for _, v in figures]
    if len(values) < 3:
        return ArithmeticCheck()
    shown = {v: text for text, v in figures}

    if _TOTAL.search(claim):
        for i, total in enumerate(values):
            rest = values[:i] + values[i + 1 :]
            if _close(total, sum(rest, Decimal(0))):
                return ArithmeticCheck(
                    checked=True, reason=f"the total {shown[total]} is the sum of the others"
                )
        others = values[:-1]
        return ArithmeticCheck(
            checked=True,
            holds=False,
            reason=(
                f"no figure is the sum of the others: {' + '.join(shown[v] for v in others)} = "
                f"{sum(others, Decimal(0)):,}, not {shown[values[-1]]}"
            ),
        )

    if _DIFFERENCE.search(claim):
        for result in values:
            for a, b in permutations([v for v in values if v is not result], 2):
                if a > b and _close(a - b, result):
                    return ArithmeticCheck(
                        checked=True,
                        reason=f"{shown[a]} - {shown[b]} = {shown[result]}, as the claim states",
                    )
        pairs = [(max(a, b), min(a, b)) for a, b in combinations(values, 2) if a != b]
        computed = ", ".join(f"{shown[a]} - {shown[b]} = {a - b:,}" for a, b in pairs[:3])
        return ArithmeticCheck(
            checked=True,
            holds=False,
            reason=f"no figure is the difference of two others ({computed})",
        )
    return ArithmeticCheck()


def is_computed(claim: str, figure: str) -> bool:
    """Whether `figure`, as the claim writes it, is the difference of two of the claim's other
    figures or the sum of all of them. Such a figure is on no cited line - it was worked out - and
    is grounded by the figures it was worked out from, when those are."""
    figures = find_figures(claim)
    target = next((v for text, v in figures if text == figure), None)
    if target is None:
        return False
    others = [v for text, v in figures if text != figure]
    if len(others) >= 2 and _close(target, sum(others, Decimal(0))):
        return True
    return any(a > b and _close(a - b, target) for a, b in permutations(others, 2))
