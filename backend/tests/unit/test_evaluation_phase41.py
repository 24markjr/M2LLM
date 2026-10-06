"""Phase 41: repeated runs with spread, Experiment 006's scoring, and the scenarios that measure.

The scorers are pure and tested exactly, as the Phase 20 ones are. The scenario checks hold the
dataset itself to account: a scenario naming a document that does not exist, or an operation the
vocabulary does not have, would run and score - just not what its author meant.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest
import yaml

from app.core.config import get_settings
from app.evaluation.metrics import MetricSet
from app.evaluation.report import EvalReport, ScenarioReport, spread, spread_to_markdown
from app.evaluation.retrieval import (
    Hit,
    RetrievalQuery,
    load_benchmark,
    run_retrieval_experiment,
    score_query,
    summarise,
    to_markdown,
)
from app.evaluation.runner import datasets_dir
from app.intelligence.context.store import fuse
from app.intelligence.trust.specifics import values_out_of_context
from app.llm.echo import EchoProvider
from app.schemas.intent import Operation
from app.schemas.trust import EvidenceText
from app.tools.loader import load_documents, resolve_document

# --- repeated runs ---------------------------------------------------------------------


def _run(coverage: float, *, findings: int = 1, claims: float = 1.0) -> EvalReport:
    return EvalReport(
        suite="all",
        model="m",
        config_hash="c",
        scenarios=[
            ScenarioReport(
                scenario_id="s",
                metrics=MetricSet(),
                findings=findings,
                is_positive_case=True,
                expected_claims_found=claims,
            )
        ],
        aggregate=MetricSet(evidence_coverage=coverage, intent_accuracy=0.5),
    )


def test_the_spread_reports_mean_deviation_and_range() -> None:
    summary = spread([_run(1.0), _run(0.9), _run(0.8)], {"evidence_coverage": 0.03})
    coverage = next(m for m in summary.metrics if m.metric == "evidence_coverage")
    assert coverage.mean == pytest.approx(0.9)
    assert coverage.stdev == pytest.approx(0.1)
    assert (coverage.minimum, coverage.maximum) == (0.8, 1.0)
    # Ranges wider than the regression tolerance are called out: one run cannot be checked.
    assert coverage.noisier_than_tolerance
    steady = next(m for m in summary.metrics if m.metric == "intent_accuracy")
    assert steady.stdev == 0.0 and not steady.noisier_than_tolerance


def test_a_scenario_that_changes_its_verdict_is_unstable() -> None:
    summary = spread([_run(1.0, claims=1.0), _run(1.0, claims=0.0)], {})
    assert not summary.scenarios[0].stable
    assert summary.scenarios[0].expected_claims_found == [1.0, 0.0]
    assert "| s | 1, 1 | 1.00, 0.00 | - | NO |" in spread_to_markdown(summary)


def test_runs_of_different_systems_are_not_combined() -> None:
    other = _run(1.0)
    other.model = "another"
    with pytest.raises(ValueError):
        spread([_run(1.0), other], {})


# --- Experiment 006: scoring ----------------------------------------------------------------------


def _query(relevant: list[str]) -> RetrievalQuery:
    return RetrievalQuery(id="q", kind="paraphrase", query="x", relevant=relevant)


DOCS = {"a.txt": "heading\nthe answer is here\nother", "b.txt": "unrelated"}


def test_a_citation_counts_only_at_the_exact_line() -> None:
    hits = [
        Hit(document_id="a.txt", line=1, text="heading\nthe answer is here", score=0.9),
        Hit(document_id="a.txt", line=2, text="the answer is here", score=0.8),
    ]
    result = score_query(_query(["a.txt:r2"]), hits, DOCS)
    assert result.first_relevant_rank == 2 and result.first_relevant_score == 0.8
    assert result.relevant_cited == 1 and result.passage_hit


def test_the_right_paragraph_cited_at_the_wrong_line_is_a_passage_hit_only() -> None:
    hits = [Hit(document_id="a.txt", line=1, text="heading\nthe answer is here", score=0.9)]
    result = score_query(_query(["a.txt:r2"]), hits, DOCS)
    assert result.first_relevant_rank is None
    assert result.passage_hit


def test_the_summary_separates_answers_from_non_answers() -> None:
    answered = score_query(
        _query(["a.txt:r2"]), [Hit(document_id="a.txt", line=2, text="x", score=0.9)], DOCS
    )
    missed = score_query(
        _query(["a.txt:r2"]), [Hit(document_id="b.txt", line=1, text="x", score=0.7)], DOCS
    )
    nothing = score_query(_query([]), [Hit(document_id="b.txt", line=1, text="x", score=0.8)], DOCS)
    arm = summarise("semantic-lines", [answered, missed, nothing], semantic=True)
    assert (arm.hit_at_1, arm.hit_at_5, arm.mrr) == (0.5, 0.5, 0.5)
    assert arm.best_unanswerable_score == 0.8
    assert arm.answerable_above_it == 0.5  # only the 0.9 answer clears the non-answer's 0.8


def test_rank_fusion_rewards_agreement_and_ignores_score_scales() -> None:
    lexical = [("a", 1), ("b", 1), ("c", 1)]
    semantic = [("b", 1), ("d", 1), ("a", 1)]
    fused = [key for key, _ in fuse([lexical, semantic])]
    assert fused[:2] == [("b", 1), ("a", 1)]  # both lists ranked these
    assert set(fused) == {("a", 1), ("b", 1), ("c", 1), ("d", 1)}
    assert fuse([[("a", 1), ("a", 1)]]) == fuse([[("a", 1)]])  # a duplicate does not count twice


async def test_the_experiment_runs_end_to_end_and_says_when_it_measured_nothing() -> None:
    report = await run_retrieval_experiment(EchoProvider(), arms=("lexical", "semantic-lines"))
    assert report.meaningless
    assert [a.arm for a in report.arms] == ["lexical", "semantic-lines"]
    assert report.arms[1].chunks > 0
    assert "measure the plumbing" in to_markdown(report)


# --- the datasets ----------------------------------------------------------------------


def test_every_benchmark_citation_points_at_a_real_line() -> None:
    corpus, queries = load_benchmark()
    documents, _ = load_documents([resolve_document(name) for name in corpus])
    assert sorted(documents) == sorted(corpus)
    for query in queries:
        for document_id, line in query.relevant_lines():
            lines = documents[document_id].splitlines()
            assert 0 < line <= len(lines) and lines[line - 1].strip(), (query.id, document_id, line)
    kinds = {q.kind for q in queries}
    assert kinds == {"keyword", "paraphrase", "unanswerable"}


def test_every_scenario_names_real_documents_and_known_operations() -> None:
    fixtures = get_settings().agent_dir / "fixtures"
    vocabulary = {o.value for o in Operation}
    paths = sorted(datasets_dir().glob("*.yaml"))
    assert len(paths) == 14
    for path in paths:
        raw = yaml.safe_load(path.read_text(encoding="utf-8"))
        assert raw["id"] == path.stem
        for name in raw["documents"]:
            assert (fixtures / "documents" / name).exists() or (fixtures / "csv" / name).exists(), (
                path.stem,
                name,
            )
        unknown = set(raw.get("expected_operations", [])) - vocabulary
        assert not unknown, (path.stem, unknown)
        # A scenario either plants something, says there is nothing, or measures gaps; never both.
        assert not (raw.get("expected_claims") and raw.get("expect_zero_findings")), path.stem


def test_the_orion_scenarios_read_through_the_new_parsers() -> None:
    raw = {
        p.stem: yaml.safe_load(p.read_text(encoding="utf-8"))
        for p in datasets_dir().glob("orion_*.yaml")
    }
    suffixes = {Path(d).suffix for scenario in raw.values() for d in scenario["documents"]}
    assert {".docx", ".xlsx", ".png", ".srt"} <= suffixes
    assert raw["orion_meeting_consistent"]["expect_zero_findings"] is True


# --- invariants -----------------------------------------------------------------------------------


def test_evaluation_never_gives_a_mission_stored_retrieval() -> None:
    """The baseline stays lexical (Phase 40): a scenario run must not pass a retriever, or the
    numbers would change with whatever a developer's workspace happened to hold."""
    source = (Path(__file__).parents[2] / "app" / "evaluation" / "runner.py").read_text("utf-8")
    calls = [
        node
        for node in ast.walk(ast.parse(source))
        if isinstance(node, ast.Call) and getattr(node.func, "id", "") == "run_mission"
    ]
    assert calls and all("retriever" not in {k.arg for k in c.keywords} for c in calls)


def test_tools_reach_no_store_and_no_integration() -> None:
    """Tools read data they are given (Phase 40 kept it so): no tool imports a store or a seam."""
    tools = Path(__file__).parents[2] / "app" / "tools"
    for path in tools.glob("*.py"):
        tree = ast.parse(path.read_text("utf-8"))
        imported = {
            node.module or "" for node in ast.walk(tree) if isinstance(node, ast.ImportFrom)
        } | {
            alias.name
            for node in ast.walk(tree)
            if isinstance(node, ast.Import)
            for alias in node.names
        }
        bad = {m for m in imported if m.startswith(("app.integrations", "app.database", "app.api"))}
        assert not bad, (path.name, bad)


# --- BUG-027: a value taken from a line about something else -------------------------------------


def _ev(source: str, content: str) -> EvidenceText:
    return EvidenceText(source=source, content=content)


def _fixtures(*names: str) -> dict[str, str]:
    documents, _ = load_documents([resolve_document(name) for name in names])
    return documents


def _cite(documents: dict[str, str], ref: str) -> EvidenceText:
    document, _, row = ref.rpartition(":r")
    line = documents[document].splitlines()[int(row) - 1]
    return _ev(ref, f"{ref}: {line}")


def test_the_two_phase41_confabulations_are_contradicted_by_their_own_documents() -> None:
    aurora = _fixtures("aurora_project_report.txt")
    assert values_out_of_context(
        "The Aurora project report states two different completion dates: 30 April 2026 and "
        "20 April 2026",
        [
            _cite(aurora, "aurora_project_report.txt:r10"),
            _cite(aurora, "aurora_project_report.txt:r4"),  # "Date: 20 April 2026"
        ],
        aurora,
    ) == ["20 April 2026"]

    orion = _fixtures("orion_meeting.srt", "orion_minutes.docx")
    assert values_out_of_context(
        "The Orion site readiness meeting recording states the handover date as 6 April 2026, "
        "while the written minutes state it as 1 April 2026",
        [
            _cite(orion, "orion_meeting.srt:r3"),
            _cite(orion, "orion_minutes.docx:r3"),  # the installation line
        ],
        orion,
    ) == ["1 April 2026"]


def test_an_unrelated_line_whose_value_its_document_confirms_is_kept() -> None:
    """The first version of BUG-027's rule dropped this real contradiction (Phase 41 baseline):
    "- M4 Production readiness: 30 April 2026" shares no word with "approved completion date",
    but the report's completion line says 30 April too."""
    documents = _fixtures("aurora_project_report.txt", "aurora_financial_report.txt")
    claim = (
        "The project's approved completion date is 30 April 2026 according to the project report, "
        "but the financial report states the completion date as 14 May 2026"
    )
    cited = [
        _cite(documents, "aurora_project_report.txt:r15"),
        _cite(documents, "aurora_financial_report.txt:r12"),
    ]
    assert values_out_of_context(claim, cited, documents) == []


@pytest.mark.parametrize(
    ("claim", "refs"),
    [
        # The real contradictions of the existing scenarios.
        (
            "Shipment 4821 arrived on 14 September according to one report and on 16 September "
            "according to the other",
            ["shipment_report_a.txt:r1", "shipment_report_b.txt:r1"],
        ),
        (
            "The target completion date is 2026-04-30 but milestone M4 closed on 2026-05-14",
            ["project_report.txt:r10", "milestone_report.txt:r7"],
        ),
        # A table row carries its meaning in the header: never judged by its own words.
        ("Helix spend of 450,000 was never approved", ["budget.csv:r2"]),
        (
            "The recorded spend of INR 287,500 exceeds the approved INR 250,000",
            ["orion_ledger.xlsx:r7", "orion_budget_memo.docx:r4"],
        ),
    ],
)
def test_values_on_lines_about_them_are_in_context(claim: str, refs: list[str]) -> None:
    documents = _fixtures(*{ref.rpartition(":r")[0] for ref in refs})
    cited = [_cite(documents, ref) for ref in refs]
    assert values_out_of_context(claim, cited, documents) == []


def test_without_documents_nothing_can_be_contradicted() -> None:
    cited = [_ev("a.txt:r1", "Date: 20 April 2026")]
    assert values_out_of_context("x on 20 April 2026", cited) == []


# --- BUG-028: a spreadsheet row's date and column separator read as one amount --------------------


@pytest.mark.parametrize(
    ("line", "amounts"),
    [
        ("Cooling units (36),Polar Systems,2026-03-19,162000", ["162000"]),
        ("Commissioning,Polar Systems,2026-04-01,26000", ["26000"]),
        ("The approved project budget is INR 380,000.", ["380,000"]),
        ("$1,234.50 and 450000", ["$1,234.50", "450000"]),
        ("Date: 20 April 2026", []),
        ("M4 go-live closed 2026-05-14.", []),
    ],
)
def test_amounts_respect_digit_grouping_and_never_read_a_date(
    line: str, amounts: list[str]
) -> None:
    from app.tools.builtin import _amounts

    assert _amounts(line) == amounts


def test_a_difference_of_two_cited_figures_is_grounded() -> None:
    from app.intelligence.trust.specifics import ungrounded_specifics

    evidence = [
        _ev("orion_ledger.xlsx:p1", "Total spend,,,287500"),
        _ev("orion_budget_memo.docx:r4", "approved a total budget of INR 250,000"),
    ]
    claim = "The recorded spend exceeded the approved budget by INR 37,500"
    assert ungrounded_specifics(claim, evidence) == []
    assert ungrounded_specifics("It exceeded it by INR 40,000", evidence) == ["40,000"]


@pytest.mark.parametrize(
    ("claim", "value"),
    [
        (
            "The report states 30 April 2026 as the approved completion date at r10, but also "
            "states 30 April 2026 at r15, indicating a single date",
            "30 April 2026",
        ),
        ("Both documents give the budget as 380,000 and 380,000", "380,000"),
        ("Shipment 4821 arrived on 14 September in one report and 16 September in the other", ""),
        ("Spend of 287,500 exceeds the approved 250,000", ""),
        ("The completion date is 30 April 2026", ""),
    ],
)
def test_the_same_value_on_every_side_is_agreement(claim: str, value: str) -> None:
    from app.intelligence.trust.specifics import single_value

    assert single_value(claim) == value


def test_inflections_of_the_same_word_are_shared_context() -> None:
    claim = "The report gives 30 April 2026 and the finance file 14 May 2026 for completion."
    documents = {
        "report.txt": "Date: 1 March 2026\nTarget completion 30 April 2026.",
        "finance.txt": "Delivery completed 14 May 2026.\nIssued 2 June 2026.",
    }
    evidence = [
        _ev("report.txt:r2", "Target completion 30 April 2026."),
        _ev("finance.txt:r1", "Delivery completed 14 May 2026."),
    ]
    assert values_out_of_context(claim, evidence, documents) == []


def test_the_text_at_a_page_merges_every_observation_that_cited_it() -> None:
    """BUG-029: the last observation to cite a page replaced what earlier ones found there."""
    from app.intelligence.replanning.controller import evidence_text_map
    from app.schemas.common import SourceLocator
    from app.schemas.evidence import Evidence

    def page(content: str, task: str) -> Evidence:
        return Evidence(
            evidence_id=f"E-00{task[-1]}",
            locator=SourceLocator(document_id="l.xlsx", document_name="l.xlsx", page=1),
            content=f"l.xlsx:p1: {content}",
            retrieved_by_task_id=task,
        )

    text = evidence_text_map(
        [page("Total spend,,,287500", "t1"), page("Cooling,2026-03-19,162000", "t2")]
    )
    assert "287500" in text["l.xlsx:p1"] and "162000" in text["l.xlsx:p1"]
    assert text["l.xlsx:p1"].startswith("l.xlsx:p1: ")
