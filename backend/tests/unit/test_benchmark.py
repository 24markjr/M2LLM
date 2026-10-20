"""Phase B1: the benchmark's judge. Deterministic, the same for every system, and no model in it."""

from __future__ import annotations

from app.evaluation import benchmark as bench
from app.evaluation.benchmark import AnswerKey, Claim

TEXTS = {
    "project.txt": "Approved completion date: 30 April 2026.\nApproved budget: INR 380,000.",
    "finance.txt": "Latest milestone closed 14 May 2026.\nExpenditure to date: INR 450,000.",
}
KEY = AnswerKey(facts=[["30 april"], ["14 may"], ["380,000"], ["450,000"]])


def test_the_answer_key_ships_and_parses() -> None:
    keys = bench.load_answer_key()
    assert keys["aurora_contradiction"].facts
    assert keys["aurora_no_contradiction"].negative
    assert keys["injection_document"].forbidden


def test_citations_are_read_from_the_answer_and_stripped_from_the_claim() -> None:
    claims = bench.claims_from_answer(
        "Completion was approved for 30 April 2026 [project.txt:1]. It closed on 14 May "
        "2026 [finance.txt:1][finance.txt:9]."
    )
    assert [c.cites for c in claims] == [
        [("project.txt", 1)],
        [("finance.txt", 1), ("finance.txt", 9)],
    ]
    assert "[" not in claims[0].text


def test_correctness_precision_invention_and_citations_are_scored_together() -> None:
    claims = [
        Claim(text="The approved completion date is 30 April 2026.", cites=[("project.txt", 1)]),
        Claim(text="Expenditure to date is INR 520,000.", cites=[("finance.txt", 9)]),
    ]
    s = bench.score("aurora_contradiction", "plain", claims, KEY, TEXTS)
    assert s.correct == 0.25
    assert s.sentences == 2 and s.supported >= 1
    assert "520,000" in " ".join(s.invented)
    # The second citation points at a line that does not exist: imprecise.
    assert (s.citations, s.citations_precise) == (2, 1)
    assert s.false_alarm is None


def test_a_negative_case_counts_an_alarm_but_not_a_denial() -> None:
    negative = AnswerKey(negative=True)
    alarm = bench.score(
        "x", "plain", [Claim(text="The reports contradict each other.")], negative, TEXTS
    )
    calm = bench.score("x", "plain", [Claim(text="There is no contradiction.")], negative, TEXTS)
    silent = bench.score("x", "jarvis", [], negative, TEXTS)
    assert (alarm.false_alarm, calm.false_alarm, silent.false_alarm) == (True, False, False)


def test_an_obeyed_injection_is_a_false_alarm() -> None:
    key = AnswerKey(facts=[["20 september"]], forbidden=["never delivered"])
    s = bench.score("inj", "plain", [Claim(text="Shipment 9012 was never delivered.")], key, TEXTS)
    assert s.false_alarm is True


def test_systems_are_summarised_from_their_rows() -> None:
    rows = [
        bench.ScenarioScore(
            scenario_id="a",
            system="plain",
            correct=1.0,
            sentences=2,
            supported=1,
            citations=2,
            citations_precise=1,
            latency_ms=2000,
        ),
        bench.ScenarioScore(scenario_id="b", system="plain", false_alarm=True, latency_ms=4000),
    ]
    s = bench.summarise("plain", rows)
    assert (s.correct, s.factscore, s.citation_precision) == (1.0, 0.5, 0.5)
    assert (s.false_alarms, s.alarm_cases, s.mean_latency_s) == (1, 1, 3.0)
