"""BUG-034: the knowledge pass reads every document, the parts most relevant to the objective first,
and leaves contact details out.

Measured before the fix on twelve AURORA documents: 12 of 191 chunks read, nearly all from one PDF.
"""

from __future__ import annotations

import pytest

from app.intelligence.knowledge.extraction import Chunk, _is_contact, chunk_document
from app.intelligence.knowledge.selection import objective_terms, relevance, select_chunks


def _chunk(document: str, line: int, text: str) -> Chunk:
    return Chunk(document_id=document, lines=((line, text),))


def test_every_document_is_read_before_any_is_read_twice() -> None:
    chunks = [_chunk("first.pdf", n, f"page {n}") for n in range(1, 31)]
    chunks += [_chunk(f"doc{d}.pdf", 1, "intro") for d in range(2, 12)]
    chosen = select_chunks(chunks, 12)
    assert len(chosen) == 12
    assert {c.document_id for c in chosen} == {"first.pdf", *(f"doc{d}.pdf" for d in range(2, 12))}
    # Eleven documents read once; the twelfth slot goes back to the only one with more to read.
    assert sum(1 for c in chosen if c.document_id == "first.pdf") == 2


def test_within_a_document_the_most_relevant_part_comes_first() -> None:
    chunks = [
        _chunk("report.pdf", 1, "Cover page. Prepared by the programme office."),
        _chunk("report.pdf", 40, "Table of contents and acknowledgements."),
        _chunk("report.pdf", 80, "Security architecture: encryption keys are rotated yearly."),
        _chunk("other.pdf", 1, "Overview."),
    ]
    chosen = select_chunks(chunks, 2, "Assess the security risks of the encryption design")
    assert [(c.document_id, c.first_line) for c in chosen] == [("report.pdf", 80), ("other.pdf", 1)]


def test_dates_and_figures_count_when_the_objective_says_little() -> None:
    plain = "The programme continues as described."
    dated = "Completion is scheduled for 30 April 2026 at a cost of 380,000."
    assert relevance(dated, set()) == 1.0 and relevance(plain, set()) == 0.0


def test_what_is_read_keeps_document_order_so_names_carry_forward() -> None:
    chunks = [_chunk("a.pdf", n, "budget" if n == 3 else "x") for n in (1, 2, 3)]
    chosen = select_chunks([*chunks, _chunk("b.pdf", 1, "y")], 3, "budget")
    assert [(c.document_id, c.first_line) for c in chosen] == [
        ("a.pdf", 1),
        ("a.pdf", 3),
        ("b.pdf", 1),
    ]


def test_everything_is_read_when_it_fits() -> None:
    chunks = chunk_document("small.txt", "one\n\ntwo\n\nthree", 3000)
    assert select_chunks(chunks, 12) == chunks


def test_objective_words_exclude_the_words_every_objective_uses() -> None:
    terms = objective_terms("Determine whether the AURORA project can be trusted for deployment")
    assert {"aurora", "project", "trusted", "deployment"} <= terms
    assert not {"determine", "whether", "the"} & terms


@pytest.mark.parametrize(
    ("attribute", "value", "contact"),
    [
        ("phone", "9137815600 / 9029767757", True),
        ("contact", "pm.team@arcaisys.com", True),
        ("address", "G1603, SAMARTH GARDEN, BHANDUP (W), MUMBAI", True),
        ("homepage", "https://example.org", True),
        ("ip_address", "10.0.4.22", False),
        ("mac address", "00:1B:44:11:3A:B7", False),
        ("purchase_order", "4500012345", False),
        ("approved_budget", "INR 380,000", False),
    ],
)
def test_contact_details_are_recognised_and_technical_addresses_are_not(
    attribute: str, value: str, contact: bool
) -> None:
    assert _is_contact(attribute, value) is contact
