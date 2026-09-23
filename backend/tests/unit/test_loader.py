"""Real-input handling: large documents, and caps that are always visible.

The rule these tests enforce: **truncation is never silent.** A cap that quietly drops
evidence would let the agent conclude "no contradiction found" from material it never saw —
the exact failure this project exists to prevent. Every test here checks that the omission
is reported, not just that the output is small.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from app.schemas.tool import ToolCall
from app.tools.base import ToolContext
from app.tools.builtin import CsvAnalysisTool, DocumentExtractTool, DocumentSearchTool
from app.tools.loader import (
    MAX_CSV_ROWS,
    DocumentLoadError,
    ResultCap,
    cap,
    load_document,
    load_documents,
    load_text,
)


def _big_csv(path: Path, rows: int = 1200) -> Path:
    lines = ["item,amount,approved"]
    lines += [f"line_item_{i},{1000 + i},yes" for i in range(rows)]
    path.write_text("\n".join(lines), encoding="utf-8")
    return path


def _big_report(path: Path, lines: int = 3000) -> Path:
    body = [
        f"Line {i}: milestone M{i % 9} closed 2026-0{(i % 9) + 1}-15 costing {1000 + i}."
        for i in range(lines)
    ]
    path.write_text("\n".join(body), encoding="utf-8")
    return path


# --- the cap primitive ---------------------------------------------------------


def test_a_cap_reports_what_it_left_out() -> None:
    kept, report = cap(list(range(100)), 10)
    assert len(kept) == 10
    assert report.found == 100
    assert report.returned == 10
    assert report.capped
    assert "90 not returned" in report.note()


def test_an_uncapped_result_says_nothing() -> None:
    kept, report = cap([1, 2, 3], 10)
    assert kept == [1, 2, 3]
    assert not report.capped
    assert report.note() == ""


def test_an_empty_result_is_not_capped() -> None:
    assert not ResultCap(found=0, returned=0).capped


# --- loading -------------------------------------------------------------------


def test_a_large_text_file_is_truncated_and_says_so(tmp_path: Path) -> None:
    path = tmp_path / "huge.txt"
    path.write_text("x" * 5000, encoding="utf-8")

    document = load_text(path, max_chars=1000)

    assert document.truncated
    assert "not read" in document.omitted_note
    assert "[TRUNCATED]" in document.text, "the text itself carries the marker"


def test_a_small_file_is_loaded_whole(tmp_path: Path) -> None:
    path = tmp_path / "small.txt"
    path.write_text("a short report", encoding="utf-8")

    document = load_text(path)

    assert not document.truncated
    assert document.omitted_note == ""
    assert document.text == "a short report"


def test_a_thousand_row_csv_loads(tmp_path: Path) -> None:
    document = load_document(_big_csv(tmp_path / "budget.csv"))
    assert document.kind == "csv"
    assert document.line_count > 1000


def test_a_missing_file_raises_rather_than_loading_empty(tmp_path: Path) -> None:
    with pytest.raises(DocumentLoadError, match="no such file"):
        load_document(tmp_path / "absent.pdf")


def test_an_unreadable_file_is_skipped_not_fatal(tmp_path: Path) -> None:
    """One bad attachment must not abandon an investigation over the others."""
    good = tmp_path / "good.txt"
    good.write_text("readable", encoding="utf-8")

    documents, loaded = load_documents([good, tmp_path / "missing.txt"])

    assert set(documents) == {"good.txt"}
    assert len(loaded) == 1


def test_the_load_summary_states_what_was_read(tmp_path: Path) -> None:
    path = tmp_path / "big.txt"
    path.write_text("y" * 5000, encoding="utf-8")
    document = load_text(path, max_chars=1000)
    assert "not read" in document.summary


# --- tools under real volume ---------------------------------------------------


async def test_extraction_from_a_large_document_is_capped_and_reported(tmp_path: Path) -> None:
    """A hundred-page report yields thousands of matches; the prompt cannot take them."""
    documents, _ = load_documents([_big_report(tmp_path / "report.txt")])
    ctx = ToolContext(run_id="run_0123456789ab", document_ids=list(documents), documents=documents)

    result = await DocumentExtractTool().execute(
        ToolCall(tool_name="document_extract", arguments={"pattern": "dates and amounts"}), ctx
    )

    assert result.ok
    extractions = result.output["extractions"]
    assert len(extractions) < 5000, "the result is bounded"
    assert result.output["cap"]["found"] > len(extractions)
    assert result.output["note"], "the omission is stated, not hidden"


async def test_a_thousand_row_csv_is_analysed_by_aggregate(tmp_path: Path) -> None:
    """Analysed, not recited. The totals matter; the thousand strings do not."""
    documents, _ = load_documents([_big_csv(tmp_path / "budget.csv", rows=1200)])
    ctx = ToolContext(run_id="run_0123456789ab", document_ids=list(documents), documents=documents)

    result = await CsvAnalysisTool().execute(
        ToolCall(
            tool_name="csv_analysis",
            arguments={"document_id": "budget.csv", "column": "amount"},
        ),
        ctx,
    )

    assert result.ok
    assert result.output["rows"] == 1200
    assert result.output["total"] is not None, "the aggregate is computed over every row"
    assert result.output["minimum"] is not None and result.output["maximum"] is not None
    assert len(result.output["values"]) <= MAX_CSV_ROWS
    assert result.output["cap"]["found"] == 1200


async def test_search_over_a_large_document_returns_only_the_best(tmp_path: Path) -> None:
    documents, _ = load_documents([_big_report(tmp_path / "report.txt")])
    ctx = ToolContext(run_id="run_0123456789ab", document_ids=list(documents), documents=documents)

    result = await DocumentSearchTool().execute(
        ToolCall(tool_name="document_search", arguments={"query": "milestone closed", "k": 5}), ctx
    )

    assert result.ok
    assert len(result.output["passages"]) == 5
    assert result.output["cap"]["found"] > 5
    assert result.output["note"]


async def test_capped_results_still_carry_exact_locators(tmp_path: Path) -> None:
    """Bounding the volume must not cost the provenance that makes evidence citable."""
    documents, _ = load_documents([_big_report(tmp_path / "report.txt")])
    ctx = ToolContext(run_id="run_0123456789ab", document_ids=list(documents), documents=documents)

    result = await DocumentExtractTool().execute(
        ToolCall(tool_name="document_extract", arguments={"pattern": "dates"}), ctx
    )

    assert result.sources
    assert all(":r" in source for source in result.sources)
