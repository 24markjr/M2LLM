"""Whether a calculation written out in a claim is right - computed by code, never trusted.

Measured on the VAJRA case (2026-10-30): the conversation stated "The overpayment ... is
INR 3,78,00,000 (₹4,20,00,000 - ₹3,78,00,000)" and the verifier passed it - every figure was on a
cited line. The working was written in the claim and nobody checked it: 4,20,00,000 - 3,78,00,000
is 42,00,000.

A claim is checked when it writes a subtraction or an addition with spaces around the operator
("A - B", "A minus B", "A + B") - dates (2026-04-30) and references (PV-2026-0356) have none - and
states a result: another figure outside the expression. The result must be the computed value;
`is` / `=` in between makes no difference. A claim with no stated result is left to the verifier.
"""

from __future__ import annotations

import re
from decimal import Decimal, InvalidOperation

from app.schemas.common import JarvisModel

_CURRENCY = r"(?:₹|INR|Rs\.?)?\s*"
_NUMBER = r"(\d[\d,]*(?:\.\d+)?)"
_EXPRESSION = re.compile(
    # A hyphen, a minus sign (U+2212) or an en dash: all are written for "minus".
    _CURRENCY + _NUMBER + r"\s+(-|−|–|minus|\+|plus)\s+" + _CURRENCY + _NUMBER,
    re.IGNORECASE,
)
_FIGURE = re.compile(r"(?<![\w/-])" + _NUMBER + r"(?![\w/-])")


class CalculationCheck(JarvisModel):
    checked: bool = False
    holds: bool = True
    reason: str = ""


def _value(text: str) -> Decimal | None:
    try:
        return Decimal(text.replace(",", ""))
    except InvalidOperation:
        return None


def _written_like(value: Decimal, example: str) -> str:
    """`value` grouped as `example` is: 42,00,000 beside 4,20,00,000, 42,000 beside 420,000."""
    digits = f"{abs(value):f}".split(".")[0]
    indian = bool(re.fullmatch(r"\d{1,2}(,\d{2})+,\d{3}", example))
    if not indian or len(digits) <= 3:
        return f"{value:,}"
    head, tail = digits[:-3], digits[-3:]
    pairs: list[str] = []
    while len(head) > 2:
        pairs.insert(0, head[-2:])
        head = head[:-2]
    return ("-" if value < 0 else "") + ",".join([head, *pairs, tail])


def check_calculation(claim: str) -> CalculationCheck:
    match = _EXPRESSION.search(claim)
    if match is None:
        return CalculationCheck()
    a, b = _value(match.group(1)), _value(match.group(3))
    if a is None or b is None:
        return CalculationCheck()
    subtract = match.group(2).lower() in ("-", "−", "–", "minus")
    computed = a - b if subtract else a + b
    outside = claim[: match.start()] + " " + claim[match.end() :]
    stated = [
        (m.group(1), v)
        for m in _FIGURE.finditer(outside)
        if (v := _value(m.group(1))) is not None and v >= 100
    ]
    if not stated:
        return CalculationCheck()
    operator = "-" if subtract else "+"
    working = f"{match.group(1)} {operator} {match.group(3)}"
    shown = _written_like(computed, match.group(1))
    if any(value == computed for _, value in stated):
        return CalculationCheck(checked=True, reason=f"{working} = {shown}")
    return CalculationCheck(
        checked=True,
        holds=False,
        reason=(
            f"{working} is {shown}, not {', '.join(written for written, _ in stated)} as the "
            "claim states"
        ),
    )
