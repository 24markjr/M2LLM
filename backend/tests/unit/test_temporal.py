"""The shared date, time, identifier and number parser (Phase 25).

Both teammates parsed time on their own, and each version had a defect the other did not:
Member 3 forced every date to 2026, and Member 4 compared clock times as strings and could not
see dates at all. These tests pin the behaviour that replaced both.
"""

from __future__ import annotations

import pytest

from app.intelligence.temporal import (
    compare_dates,
    dates_disjoint,
    find_dates,
    find_figures,
    find_times,
    identifiers,
    parse_date,
    parse_number,
    same_time,
    sort_key,
    times_disjoint,
)
from app.schemas.knowledge import ClaimOrder, PartialDate

# --- dates --------------------------------------------------------------------


@pytest.mark.parametrize(
    ("text", "iso"),
    [
        # Member 3's six formats.
        ("14 September", "--09-14"),
        ("14 September 2026", "2026-09-14"),
        ("September 14", "--09-14"),
        ("September 14, 2026", "2026-09-14"),
        ("30/04/2026", "2026-04-30"),
        ("30-04-2026", "2026-04-30"),
        # Additions.
        ("2026-04-30", "2026-04-30"),
        ("14th Sept. 2025", "2025-09-14"),
        ("April 2026", "2026-04"),
        ("arrived on 1 May at noon", "--05-01"),
    ],
)
def test_every_supported_format_parses(text: str, iso: str) -> None:
    date = parse_date(text)
    assert date is not None
    assert date.iso() == iso


def test_a_stated_year_is_never_replaced() -> None:
    """Member 3's `dt.replace(year=2026)` turned 2025 into 2026."""
    date = parse_date("14 September 2025")
    assert date is not None and date.year == 2025


def test_a_missing_year_stays_missing() -> None:
    date = parse_date("14 September")
    assert date is not None and date.year is None


@pytest.mark.parametrize("text", ["31 February", "45 March", "13/13/2026", "Phase 2", ""])
def test_impossible_dates_and_non_dates_are_rejected(text: str) -> None:
    assert parse_date(text) is None


def test_29_february_is_allowed_without_a_year() -> None:
    assert parse_date("29 February") is not None


def test_several_dates_are_found_in_order_without_double_counting() -> None:
    text = "From 15 January 2026 to 30 April 2026, then May 2026"
    found = [d.iso() for _, d in find_dates(text)]
    assert found == ["2026-01-15", "2026-04-30", "2026-05"]


def test_compatibility_treats_an_unknown_field_as_unknown() -> None:
    full = PartialDate(year=2026, month=9, day=14)
    assert full.compatible(PartialDate(month=9, day=14))
    assert full.compatible(PartialDate(year=2026, month=9))
    assert not full.compatible(PartialDate(month=9, day=16))
    assert not full.compatible(PartialDate(year=2025, month=9, day=14))


def test_compare_orders_dates_and_refuses_false_precision() -> None:
    a, b = PartialDate(year=2026, month=4, day=30), PartialDate(year=2026, month=5, day=14)
    assert compare_dates(a, b) is ClaimOrder.A_BEFORE_B
    assert compare_dates(b, a) is ClaimOrder.A_AFTER_B
    assert compare_dates(a, a) is ClaimOrder.SAME_TIME
    # Compatible but at different granularity: calling them the same time would claim a
    # precision neither source gave.
    assert compare_dates(a, PartialDate(year=2026, month=4)) is ClaimOrder.UNKNOWN


def test_unparsed_dates_sort_last() -> None:
    keys = sorted([sort_key(None, 2026), sort_key(PartialDate(month=9, day=14), 2026)])
    assert keys[-1] == sort_key(None, 2026)


def test_an_inferred_year_is_used_only_for_ordering() -> None:
    date = PartialDate(month=9, day=14)
    assert sort_key(date, 2026) == (0, 2026, 9, 14)
    assert date.year is None


def test_dates_disjoint_needs_dates_on_both_sides() -> None:
    sep14, sep16 = PartialDate(month=9, day=14), PartialDate(month=9, day=16)
    assert dates_disjoint([sep14], [sep16])
    assert not dates_disjoint([sep14], [sep14, sep16])
    assert not dates_disjoint([], [sep16])


# --- times --------------------------------------------------------------------


def test_times_fold_am_and_pm_into_a_24_hour_clock() -> None:
    assert find_times("in at 10:15 AM, out at 1:15 pm, again 12:30 am") == [
        (10, 15, True),
        (13, 15, True),
        (0, 30, True),
    ]


def test_a_time_without_am_or_pm_matches_either() -> None:
    """Member 4 compared "11:40" and "11:40am" as strings, so they conflicted."""
    assert same_time((11, 40, False), (11, 40, True))
    assert same_time((11, 40, False), (23, 40, True))
    assert not same_time((11, 40, True), (23, 40, True))
    assert not times_disjoint(find_times("at 11:40"), find_times("at 11:40 AM"))


def test_different_times_are_disjoint() -> None:
    assert times_disjoint(find_times("11:40 AM"), find_times("1:15 PM"))


def test_invalid_clock_values_are_ignored() -> None:
    assert find_times("score 25:61") == []


# --- identifiers and numbers ----------------------------------------------------


def test_identifiers_are_three_or_more_digits() -> None:
    assert identifiers("Shipment 4821, amount 5620, item 42") == {"4821", "5620"}


def test_a_year_inside_a_date_is_not_an_identifier() -> None:
    """Member 4 read "2026" as a shared id, so two unrelated dated statements could conflict."""
    assert identifiers("Completion 30 April 2026") == set()
    assert identifiers("Shipment 4821 arrived 14 September 2026") == {"4821"}


@pytest.mark.parametrize(
    ("value", "number"),
    [
        ("INR 380,000", "380000"),
        ("380000", "380000"),
        ("$1,200.50", "1200.50"),
        ("450,000 INR", "450000"),
    ],
)
def test_single_numbers_parse_with_currency_removed(value: str, number: str) -> None:
    parsed = parse_number(value)
    assert parsed is not None and str(parsed) == number


@pytest.mark.parametrize("value", ["Phase 2 of 3", "14 September", "approved", ""])
def test_values_that_are_not_one_number_do_not_parse(value: str) -> None:
    assert parse_number(value) is None


# --- figures (A15) --------------------------------------------------------------


@pytest.mark.parametrize(
    ("text", "figures"),
    [
        ("Total spend 450,000 against INR 380,000", ["450000", "380000"]),
        ("migration,450000,no", ["450000"]),
        ("Development,Software engineering,180000", ["180000"]),
        ("1,200.50 recorded", ["1200.50"]),
        ("Shipment 4821 (amount 5620)", ["4821", "5620"]),
    ],
)
def test_figures_are_read_by_value(text: str, figures: list[str]) -> None:
    assert [str(value) for _, value in find_figures(text)] == figures


@pytest.mark.parametrize(
    "text", ["milestone r10 on 30 April 2026", "M4 phase 3 of 2 reports", "2026-04-30"]
)
def test_labels_counts_and_dates_are_not_figures(text: str) -> None:
    assert find_figures(text) == []
