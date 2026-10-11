"""The currency and unit check (Phase 51, closing Phase 41's known issue): UNIT_MISMATCH.

A finding can say "$287,500" where every line it cites says INR - the model reaching for the most
common currency. The number matches, so the figure check passes, and the claim is still wrong.

Deterministic and narrow: it reads the currencies (symbols, codes, words, lakh and crore) a claim
names and the ones its cited lines name. When both name currencies and they share none, the claim's
unit is not its evidence's. A claim naming no currency is not checked - it asserts none.
"""

from __future__ import annotations

import re

_CURRENCIES: dict[str, re.Pattern[str]] = {
    "INR": re.compile(
        r"₹|\bINR\b|\bRs\.?(?=\s|\d)|\brupees?\b|\blakhs?\b|\bcrores?\b", re.IGNORECASE
    ),
    "USD": re.compile(r"\$|\bUSD\b|\bUS\s?dollars?\b|\bdollars?\b", re.IGNORECASE),
    "EUR": re.compile(r"€|\bEUR\b|\beuros?\b", re.IGNORECASE),
    "GBP": re.compile(r"£|\bGBP\b|\bpounds? sterling\b", re.IGNORECASE),
}


def currencies(text: str) -> set[str]:
    """The currencies a text names."""
    return {code for code, pattern in _CURRENCIES.items() if pattern.search(text)}


def unit_mismatch(claim: str, cited_text: list[str]) -> str:
    """Why the claim's currency is not its evidence's, or "" when it is (or either names none)."""
    claimed = currencies(claim)
    evidenced = set().union(*(currencies(t) for t in cited_text)) if cited_text else set()
    if not claimed or not evidenced or claimed & evidenced:
        return ""
    return (
        f"the claim states {', '.join(sorted(claimed))} where its cited lines state "
        f"{', '.join(sorted(evidenced))}"
    )
