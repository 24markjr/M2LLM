"""v4 Phase 7: asking in Indian languages, answers and reports in them, and the language routes."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
from httpx import ASGITransport, AsyncClient

from app import language
from app.api.app import create_app
from app.auth.models import Role
from app.auth.permissions import allowed
from app.conversation import language as talk_language
from app.conversation import service
from app.conversation.service import AnswerClaim, Step
from app.language.detect import LANGUAGES
from app.ops import governance
from app.reporting.document import Block, Cell, ReportDocument
from app.reporting.translate import translated
from app.schemas.language import Language
from tests.unit.test_conversation import CASE, MODEL, script  # noqa: F401 - the fixture

HINDI_QUESTION = "परियोजना कब पूरी हुई?"


class Engine:
    """Stands in for IndicTrans2 in both directions, and records what it was asked."""

    def __init__(self) -> None:
        self.asked: list[tuple[str, str, list[str]]] = []

    def translate(self, lines: list[str], source: Language, target: Language) -> list[str]:
        self.asked.append((source.code, target.code, list(lines)))
        if target.code == "en":
            return [
                "When was the project completed?" if x == HINDI_QUESTION else f"EN {x}"
                for x in lines
            ]
        return [f"हिंदी: {line}" for line in lines]

    def version(self, target: str = "en") -> str:
        return f"fake@{target}"


@pytest.fixture
def engine(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Engine:
    fake = Engine()
    monkeypatch.setattr(language, "get_indictrans", lambda: fake)
    monkeypatch.setattr(governance, "_policy_path", lambda: tmp_path / "policy.json")
    return fake


def _answer() -> list[Step]:
    return [
        Step(
            action="answer",
            claims=[
                AnswerClaim(
                    text="Aurora was due on 30 April 2026.", citations=["project_report.txt:r2"]
                )
            ],
        )
    ]


async def test_a_hindi_question_runs_in_english_and_is_answered_in_hindi(
    script: dict[str, Any],  # noqa: F811 - the fixture
    engine: Engine,
) -> None:
    script["steps"] += _answer()
    thread = await service.converse(CASE, HINDI_QUESTION, MODEL)
    user, answer = thread.turns

    # The investigation read the English; the person's words are kept.
    assert user.language == "hi"
    assert user.original_text == HINDI_QUESTION
    assert user.text == "When was the project completed?"
    assert "When was the project completed?" in script["prompts"][0]
    assert HINDI_QUESTION not in script["prompts"][0]

    # The verified English is the master; the Hindi is its labelled translation.
    assert answer.claims[0].status == "SUPPORTED"
    assert answer.translation is not None
    assert answer.translation.language == "hi" and answer.translation.speech == "hi-IN"
    assert answer.translation.text.startswith("हिंदी: ")
    assert answer.translation.label == talk_language.LABEL
    assert answer.translation.engine == "indictrans2"


async def test_an_english_question_costs_no_translation(
    script: dict[str, Any],  # noqa: F811
    engine: Engine,
) -> None:
    script["steps"] += _answer()
    thread = await service.converse(CASE, "When was Aurora due?", MODEL)
    assert thread.turns[0].language == "en" and thread.turns[1].translation is None
    assert engine.asked == []


async def test_an_english_question_can_be_answered_in_the_chosen_language(
    script: dict[str, Any],  # noqa: F811
    engine: Engine,
) -> None:
    script["steps"] += _answer()
    thread = await service.converse(CASE, "When was Aurora due?", MODEL, language="ta")
    assert thread.turns[0].text == "When was Aurora due?"
    translation = thread.turns[1].translation
    assert translation is not None and translation.language == "ta"


async def test_a_roman_script_question_is_transliterated_then_translated(
    script: dict[str, Any],  # noqa: F811
    engine: Engine,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def fake_transliterate(text: str, lang: Language, *_: Any) -> tuple[str, str]:
        return HINDI_QUESTION, "local model test"

    monkeypatch.setattr(talk_language, "transliterate", fake_transliterate)
    script["steps"] += _answer()
    thread = await service.converse(CASE, "pariyojana kab poori hui?", MODEL, language="hi")
    user = thread.turns[0]
    assert user.transliterated == HINDI_QUESTION
    assert user.transliteration_engine == "local model test"
    assert user.text == "When was the project completed?"
    assert user.original_text == "pariyojana kab poori hui?"


def test_roman_hindi_is_told_from_english() -> None:
    hindi = LANGUAGES["hi"]
    assert talk_language.looks_roman("kitna bhugtan hua aur kab hua?", hindi)
    assert not talk_language.looks_roman("What was the payment and when was it made?", hindi)
    assert not talk_language.looks_roman("कितना भुगतान हुआ?", hindi)
    assert not talk_language.looks_roman("anything", LANGUAGES["en"])


# --- the report in an Indian language -----------------------------------------------------------


async def test_a_translated_report_keeps_quotes_ids_and_hashes_as_written(engine: Engine) -> None:
    document = ReportDocument(
        title="Investigation report",
        subtitle="Did the M3 dates agree?",
        facts=[("Report", "RPT-0001"), ("Objective", "Did the M3 dates agree?")],
        blocks=[
            Block(kind="heading", text="Findings"),
            Block(
                kind="table",
                columns=["ID", "Finding"],
                rows=[[Cell(text="F-001"), Cell(text="The dates differ.")]],
            ),
            Block(
                kind="pair",
                text="F-001: The dates differ.",
                left=("report_hi.txt:r7", "पाइपलाइन का कार्य 15 मई 2026 को पूरा हुआ।"),
                right=("register.txt:r8", "M3 | Pipeline laying | 2026-06-02"),
            ),
            Block(kind="facts", facts=[("Receipt hash", "ab12cd34 ef56ab78")]),
        ],
        footer="RPT-0001",
    )
    out = await translated(document, LANGUAGES["hi"], None)

    assert out.blocks[0].text.startswith("Hindi (हिन्दी): machine translation")
    assert "The English report is the master" in out.blocks[0].text
    heading, table, pair, facts = out.blocks[1:]
    assert heading.text == "हिंदी: Findings"
    assert table.rows[0][0].text == "F-001"  # an identifier
    assert table.rows[0][1].text == "हिंदी: The dates differ."
    # The quotes are the evidence's own words.
    assert pair.left == document.blocks[2].left and pair.right == document.blocks[2].right
    assert facts.facts[0][1] == "ab12cd34 ef56ab78"
    assert out.facts[0] == ("हिंदी: Report", "RPT-0001")


# --- the routes -----------------------------------------------------------------------------------


def _client() -> AsyncClient:
    return AsyncClient(transport=ASGITransport(app=create_app()), base_url="http://t")


async def test_the_catalogue_lists_the_languages_and_the_engines(engine: Engine) -> None:
    async with _client() as client:
        body = (await client.get("/api/v1/language")).json()
    codes = {lang["code"] for lang in body["languages"]}
    assert {"hi", "ta", "bn", "en"} <= codes
    assert body["status"]["engines"]["bhashini"]["configured"] is False
    assert body["status"]["bhashini_policy"] == "off"


async def test_translate_and_speak_over_http(engine: Engine) -> None:
    async with _client() as client:
        translated_body = (
            await client.post("/api/v1/language/translate", json={"text": HINDI_QUESTION})
        ).json()
        spoken = await client.post(
            "/api/v1/language/speak", json={"text": "नमस्ते", "language": "hi"}
        )
    assert translated_body["lines"] == ["When was the project completed?"]
    assert translated_body["source"] == "hi" and translated_body["engine"] == "indictrans2"
    # Bhashini is not configured: the browser reads it aloud, and nothing leaves the device.
    assert spoken.status_code == 204 and spoken.headers["X-Engine"] == "browser"


async def test_a_translated_pdf_is_refused_with_the_formats_that_work(engine: Engine) -> None:
    async with _client() as client:
        response = await client.get(
            "/api/v1/missions/run_none/investigation-report/export/pdf?language=hi"
        )
    assert response.status_code == 422
    assert response.json()["error_code"] == "ENGLISH_ONLY_FORMAT"


def test_viewers_may_translate_and_listen_but_only_admins_see_usage() -> None:
    assert allowed(Role.VIEWER, "POST", "/api/v1/language/translate")
    assert allowed(Role.VIEWER, "POST", "/api/v1/language/speak")
    assert not allowed(Role.VIEWER, "POST", "/api/v1/language/transcribe")
    assert allowed(Role.ANALYST, "POST", "/api/v1/language/transcribe")
    assert not allowed(Role.ANALYST, "GET", "/api/v1/ops/language-usage")
    assert allowed(Role.ADMIN, "GET", "/api/v1/ops/language-usage")


async def test_a_sources_cell_stays_as_written_and_lost_figures_are_restored(
    monkeypatch: pytest.MonkeyPatch, engine: Engine
) -> None:
    """The three defects the live Hindi report showed: a list of locators translated into
    nonsense, hyphens spaced out of dates, and nothing checking that figures survived."""

    def lossy(lines: list[str], source: Language, target: Language) -> list[str]:
        return ["राशि दी गई" if "4,20,000" in x else f"हिंदी: {x}" for x in lines]

    monkeypatch.setattr(engine, "translate", lossy)
    document = ReportDocument(
        title="Report",
        subtitle="Did M3 agree?",
        blocks=[
            Block(
                kind="table",
                columns=["Finding", "Sources"],
                rows=[[Cell(text="Paid INR 4,20,000."), Cell(text="a.txt:r8, b_hi.txt:r7")]],
            )
        ],
    )
    out = await translated(document, LANGUAGES["hi"], None)
    finding, sources = out.blocks[1].rows[0]
    assert sources.text == "a.txt:r8, b_hi.txt:r7"
    assert finding.text == "राशि दी गई [figures in the original: 4,20,000]"


def test_spaced_hyphens_are_rejoined_in_dates_and_ids() -> None:
    from app.language.indictrans import _rejoin

    assert _rejoin("तिथि 2026 - 06 - 02 है, F - 001") == "तिथि 2026-06-02 है, F-001"
    assert _rejoin("before - after") == "before - after"
