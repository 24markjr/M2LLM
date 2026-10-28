"""v4 Phases 6-7: the language layer - detection, evidence-safe translation, routing, Bhashini."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import httpx
import pytest

from app import language
from app.api.app import create_app
from app.api.registry import MissionRecord, get_registry, reset_registry
from app.core.config import get_settings
from app.integrations import bhashini as bhashini_module
from app.integrations.bhashini import Bhashini, BhashiniError
from app.integrations.verification import translated_only
from app.intelligence import proof
from app.language import evidence, indictrans, routing
from app.language.detect import (
    ENGLISH,
    LANGUAGES,
    detect,
    line_script,
    to_ascii_digits,
)
from app.language.indictrans import from_devanagari, sentences_of, to_devanagari
from app.language.usage import usage_summary
from app.ops import governance
from app.review.service import requirements
from app.schemas.common import SourceLocator
from app.schemas.evidence import EvidenceRef, ResolutionStatus
from app.schemas.evidence_locker import EvidenceClassification
from app.schemas.finding import Finding
from app.schemas.language import DocumentLanguage, Language, is_translated_line
from app.schemas.objective import Objective
from app.schemas.verification import IssueType, VerificationResult, VerificationStatus
from app.tools.loader import load_documents

HINDI_REPORT = (
    "सरस्वती परियोजना - प्रगति रिपोर्ट\n"
    "\n"
    "पाइपलाइन का कार्य 15 मई 2026 को पूरा हुआ।\n"
    "ठेकेदार को ₹3,80,000 का भुगतान किया गया।\n"
    "Invoice INV-22 attached."
)


class FakeEngine:
    """Stands in for IndicTrans2: a fixed English rendering per line, and a count of calls."""

    def __init__(self, table: dict[str, str] | None = None) -> None:
        self.table = table or {}
        self.calls = 0

    def translate(self, lines: list[str], source: Language, target: Language) -> list[str]:
        self.calls += 1
        return [self.table.get(line, f"EN({source.code}) {line}") for line in lines]

    def version(self, target: str = "en") -> str:
        return "fake-indictrans@1"


@pytest.fixture
def engine(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> FakeEngine:
    fake = FakeEngine(
        {
            "सरस्वती परियोजना - प्रगति रिपोर्ट": "Saraswati project - progress report",
            "पाइपलाइन का कार्य 15 मई 2026 को पूरा हुआ।": (
                "The pipeline work was completed on 15 May 2026."
            ),
            # A translation that drops a figure: the check must catch it.
            "ठेकेदार को ₹3,80,000 का भुगतान किया गया।": "The contractor was paid in full.",
        }
    )
    monkeypatch.setattr(get_settings(), "translate_evidence", True)
    monkeypatch.setattr(language, "get_indictrans", lambda: fake)
    monkeypatch.setattr(governance, "_policy_path", lambda: tmp_path / "policy.json")
    return fake


# --- detection -----------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("text", "code"),
    [
        ("परियोजना का कार्य पूरा हुआ और भुगतान किया गया है।", "hi"),
        ("प्रकल्पाचे काम पूर्ण झाले आहे आणि देयक दिले आहे.", "mr"),
        ("திட்டம் 30 ஏப்ரல் 2026 அன்று முடிக்கப்பட்டது.", "ta"),
        ("প্রকল্পটি শেষ হয়েছে এবং অর্থ প্রদান করা হয়েছে।", "bn"),
        ("প্ৰকল্পটো সম্পূৰ্ণ হৈছে।", "as"),
        ("ప్రాజెక్ట్ పూర్తయింది.", "te"),
        ("The project was completed on 15 May 2026.", "en"),
        ("Total: 3,80,000", "en"),
    ],
)
def test_the_language_is_known_from_its_script(text: str, code: str) -> None:
    assert detect(text).code == code


def test_a_line_naming_an_invoice_in_english_is_still_hindi() -> None:
    assert line_script("Invoice INV-2231 का भुगतान किया गया") == "Deva"
    assert line_script("Vendor: Southern Systems Pvt Ltd") is None
    # Digits in an Indian script are not letters: a line of figures is not a line to translate.
    assert line_script("१५ ०५ २०२६") is None


def test_native_digits_become_ascii_before_translation() -> None:
    """Measured: Bengali `১৪ মে ২০২৬` was translated as "May 6, 2013"."""
    assert to_ascii_digits("১৪ মে ২০২৬") == "14 মে 2026"
    assert to_ascii_digits("१५ मई, ₹३,८०,०००") == "15 मई, ₹3,80,000"
    assert to_ascii_digits("௧௨") == "12"


def test_every_script_is_read_as_devanagari_and_written_back() -> None:
    tamil = "திட்டம்"
    as_devanagari = to_devanagari(tamil, "Taml")
    assert all(0x0900 <= ord(c) <= 0x097F for c in as_devanagari)
    assert from_devanagari(as_devanagari, "Taml") == tamil
    # Malayalam's chillu letters are a consonant with its vowel killed.
    assert to_devanagari("ൻ", "Mlym") == "न्"
    # Dandas are shared, never shifted into another block.
    assert to_devanagari("।", "Beng") == "।"


def test_an_abbreviation_does_not_end_a_sentence() -> None:
    """Measured: splitting `ரூ. 45,000` turned the price line into two sentences."""
    assert sentences_of("விலை ரூ. 45,000 ஆக நிர்ணயிக்கப்பட்டது.") == [
        "விலை ரூ. 45,000 ஆக நிர்ணயிக்கப்பட்டது."
    ]
    assert sentences_of("काम पूरा हुआ। भुगतान किया गया।") == ["काम पूरा हुआ।", "भुगतान किया गया।"]


def test_indictrans2_tags_cover_every_language_offered() -> None:
    tags = {lang.flores for lang in LANGUAGES.values()}
    assert {"hin_Deva", "tam_Taml", "ben_Beng", "mar_Deva", "urd_Arab", "eng_Latn"} <= tags


# --- evidence-safe translation -------------------------------------------------------------------


def test_a_hindi_document_is_read_line_aligned_with_its_original(
    engine: FakeEngine, tmp_path: Path
) -> None:
    path = tmp_path / "report_hi.txt"
    path.write_text(HINDI_REPORT, encoding="utf-8")
    texts, loaded = load_documents([path])
    read = texts["report_hi.txt"].split("\n")
    original = HINDI_REPORT.split("\n")

    assert len(read) == len(original)
    assert read[0] == "[translated:hi] Saraswati project - progress report"
    assert read[1] == ""
    assert read[2] == "[translated:hi] The pipeline work was completed on 15 May 2026."
    # English lines are the source's own words, copied as they are.
    assert read[4] == "Invoice INV-22 attached."

    reading = loaded[0].reading
    assert reading is not None
    assert reading.language == "hi" and reading.language_name == "Hindi"
    assert reading.original_text == HINDI_REPORT
    assert reading.engine == "indictrans2" and reading.engine_version == "fake-indictrans@1"
    assert reading.translated_lines == [1, 3, 4]


def test_a_figure_lost_in_translation_is_restored_and_flagged(
    engine: FakeEngine, tmp_path: Path
) -> None:
    path = tmp_path / "report_hi.txt"
    path.write_text(HINDI_REPORT, encoding="utf-8")
    texts, loaded = load_documents([path])
    line = texts["report_hi.txt"].split("\n")[3]
    assert line == (
        "[translated:hi] The contractor was paid in full. [figures in the original: 3,80,000]"
    )
    assert loaded[0].reading is not None and loaded[0].reading.unsafe_lines == [4]


def test_figures_are_compared_by_value_not_by_grouping() -> None:
    assert evidence.checked("₹३,८०,००० दिए", "Paid ₹380,000")[1]
    assert evidence.checked("15 मई 2026", "15th May 2026")[1]
    assert not evidence.checked("15 मई 2026", "15 May 2016")[1]


def test_a_translation_is_made_once_and_then_read_from_the_cache(
    engine: FakeEngine, tmp_path: Path
) -> None:
    path = tmp_path / "report_hi.txt"
    path.write_text(HINDI_REPORT, encoding="utf-8")
    first, _ = load_documents([path])
    calls = engine.calls
    again, _ = load_documents([path])
    assert again == first
    assert engine.calls == calls


def test_an_english_document_is_untouched(engine: FakeEngine, tmp_path: Path) -> None:
    path = tmp_path / "ledger.txt"
    path.write_text("Total spend INR 4,20,000", encoding="utf-8")
    texts, loaded = load_documents([path])
    assert texts["ledger.txt"] == "Total spend INR 4,20,000"
    assert loaded[0].reading is None
    assert engine.calls == 0


def test_a_long_document_is_translated_up_to_the_cap_and_says_so(
    engine: FakeEngine, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(get_settings(), "max_translated_lines", 2)
    path = tmp_path / "long_hi.txt"
    path.write_text("\n".join(f"पंक्ति संख्या {i} है" for i in range(5)), encoding="utf-8")
    texts, loaded = load_documents([path])
    lines = texts["long_hi.txt"].split("\n")
    assert sum(is_translated_line(line) for line in lines) == 2
    assert loaded[0].reading is not None and loaded[0].reading.untranslated_lines == 3


def test_without_an_engine_the_document_is_read_as_written_and_says_why(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    class Missing:
        def version(self, target: str = "en") -> str:
            return "x"

        def translate(self, *args: Any) -> list[str]:
            raise indictrans.TranslationUnavailable("translation needs the media extra")

    monkeypatch.setattr(get_settings(), "translate_evidence", True)
    monkeypatch.setattr(language, "get_indictrans", lambda: Missing())
    path = tmp_path / "report_hi.txt"
    path.write_text(HINDI_REPORT, encoding="utf-8")
    texts, loaded = load_documents([path])
    assert texts["report_hi.txt"] == HINDI_REPORT
    assert "not translated from Hindi" in loaded[0].omitted_note
    assert loaded[0].reading is not None and not loaded[0].reading.translated


# --- trust: machine translation alone is never auto-verified -------------------------------------


def _finding(*sources: str) -> Finding:
    return Finding(
        finding_id="F-001",
        claim="M3 closed on 15 May 2026 per the report but on 2 June 2026 per the register.",
        evidence=[
            EvidenceRef(
                locator=SourceLocator(
                    document_id=s.split(":")[0],
                    document_name=s.split(":")[0],
                    row=int(s.split(":r")[1]),
                ),
                resolution=ResolutionStatus.RESOLVED,
            )
            for s in sources
        ],
    )


TEXT = {
    "report_hi.txt:r3": "report_hi.txt:r3: [translated:hi] The work was completed on 15 May 2026.",
    "register.txt:r7": "register.txt:r7: M3 | Pipeline laying | 2026-06-02",
}
SUPPORTED = VerificationResult(status=VerificationStatus.SUPPORTED, confidence=0.9)


def test_a_finding_resting_only_on_translation_needs_review() -> None:
    result = translated_only(_finding("report_hi.txt:r3"), TEXT, SUPPORTED)
    assert result.status is VerificationStatus.PARTIALLY_SUPPORTED
    assert [i.issue_type for i in result.issues] == [IssueType.TRANSLATED_ONLY]

    finding = _finding("report_hi.txt:r3")
    finding.verification = result
    assert any("machine translation" in reason for reason in requirements(finding))


def test_a_cross_language_finding_citing_an_original_line_can_be_verified() -> None:
    result = translated_only(_finding("report_hi.txt:r3", "register.txt:r7"), TEXT, SUPPORTED)
    assert result.status is VerificationStatus.SUPPORTED


# --- the receipt names the engine ----------------------------------------------------------------


def _receipt(languages: dict[str, Any] | None = None) -> proof.Receipt:
    return proof.build_receipt(
        run_id="run-1",
        question="Did M3's dates agree?",
        model="qwen3:4b",
        prompt_versions={},
        started_at=None,
        finished_at=None,
        texts={"report_hi.txt": "x", "register.txt": "y"},
        evidence={},
        findings=[],
        report=None,
        tasks_planned=0,
        tasks_completed=0,
        gaps_open=0,
        languages=languages,
    )


def test_the_receipt_records_the_language_engine_and_version() -> None:
    reading = DocumentLanguage(
        language="hi",
        engine="indictrans2",
        engine_version="it2@524aade4f724",
        translated_lines=[1, 3],
        unsafe_lines=[3],
    )
    receipt = _receipt({"report_hi.txt": reading})
    assert [
        (r.name, r.engine, r.engine_version, r.translated_lines, r.unsafe_lines)
        for r in receipt.languages
    ] == [("report_hi.txt", "indictrans2", "it2@524aade4f724", 2, 1)]
    # Another engine changes the receipt's hash, and nothing else about it.
    other = _receipt({"report_hi.txt": reading.model_copy(update={"engine": "bhashini"})})
    assert other.receipt_hash != receipt.receipt_hash
    assert other.documents == receipt.documents and other.findings == receipt.findings


def test_an_english_only_receipt_hashes_as_it_did_before() -> None:
    receipt = _receipt()
    body = receipt.model_dump(mode="json", exclude={"receipt_hash", "languages"})
    expected = proof._sha256(json.dumps(body, sort_keys=True, separators=(",", ":")))
    assert receipt.receipt_hash == expected


# --- routing: confidential material never leaves -------------------------------------------------


@pytest.fixture
def bhashini_on(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setattr(get_settings(), "bhashini_user_id", "user")
    monkeypatch.setattr(get_settings(), "bhashini_api_key", "key")
    monkeypatch.setattr(governance, "_policy_path", lambda: tmp_path / "policy.json")


@pytest.mark.parametrize(
    ("setting", "level", "engines"),
    [
        ("internal", EvidenceClassification.UNCLASSIFIED, ["bhashini", "open-source"]),
        ("internal", EvidenceClassification.INTERNAL, ["bhashini", "open-source"]),
        ("internal", EvidenceClassification.CONFIDENTIAL, ["open-source"]),
        ("internal", EvidenceClassification.RESTRICTED, ["open-source"]),
        ("internal", None, ["open-source"]),
        ("unclassified", EvidenceClassification.INTERNAL, ["open-source"]),
        ("unclassified", EvidenceClassification.UNCLASSIFIED, ["bhashini", "open-source"]),
        ("off", EvidenceClassification.UNCLASSIFIED, ["open-source"]),
    ],
)
def test_routing_follows_sensitivity_and_the_organisations_policy(
    bhashini_on: None, setting: str, level: EvidenceClassification | None, engines: list[str]
) -> None:
    governance.save_policy(governance.Policy(bhashini=setting))
    assert routing.engines_for(level) == engines


def test_without_bhashini_credentials_everything_stays_open_source(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(governance, "_policy_path", lambda: tmp_path / "policy.json")
    governance.save_policy(governance.Policy(bhashini="internal"))
    assert routing.engines_for(EvidenceClassification.UNCLASSIFIED) == ["open-source"]


def test_a_case_is_as_sensitive_as_its_most_sensitive_file() -> None:
    assert (
        routing.strictest([EvidenceClassification.UNCLASSIFIED, EvidenceClassification.RESTRICTED])
        is EvidenceClassification.RESTRICTED
    )
    assert routing.strictest([EvidenceClassification.UNCLASSIFIED, None]) is (
        EvidenceClassification.CONFIDENTIAL
    )
    assert routing.strictest([]) is None


# --- Bhashini: discovery, compute, retries, fallback ---------------------------------------------


def _bhashini_server(
    failures: int = 0, refuse: bool = False
) -> tuple[httpx.MockTransport, list[str]]:
    seen: list[str] = []
    state = {"failures": failures}

    def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        if "getModelsPipeline" in str(request.url):
            seen.append("discover")
            assert request.headers["ulcaApiKey"] == "key"
            return httpx.Response(
                200,
                json={
                    "pipelineResponseConfig": [
                        {
                            "taskType": "translation",
                            "config": [{"serviceId": "ai4bharat/indictrans-v2"}],
                        }
                    ],
                    "pipelineInferenceAPIEndPoint": {
                        "callbackUrl": "https://dhruva.example/inference",
                        "inferenceApiKey": {"name": "Authorization", "value": "inference-key"},
                    },
                },
            )
        seen.append("compute")
        assert request.headers["Authorization"] == "inference-key"
        if refuse:
            return httpx.Response(401, text="bad key")
        if state["failures"] > 0:
            state["failures"] -= 1
            return httpx.Response(503)
        task = body["pipelineTasks"][0]
        assert task["config"]["serviceId"] == "ai4bharat/indictrans-v2"
        sources = [item["source"] for item in body["inputData"]["input"]]
        return httpx.Response(
            200,
            json={
                "pipelineResponse": [
                    {
                        "taskType": "translation",
                        "output": [{"source": s, "target": f"B:{s}"} for s in sources],
                    }
                ]
            },
        )

    return httpx.MockTransport(handler), seen


async def test_bhashini_discovers_once_then_computes(
    bhashini_on: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    transport, seen = _bhashini_server()
    client = Bhashini(transport)
    hindi = LANGUAGES["hi"]
    assert await client.translate(["नमस्ते", "", "धन्यवाद"], hindi, ENGLISH) == [
        "B:नमस्ते",
        "",
        "B:धन्यवाद",
    ]
    await client.translate(["फिर"], hindi, ENGLISH)
    assert seen == ["discover", "compute", "compute"]
    assert client.version("en") == "ai4bharat/indictrans-v2"
    usage = usage_summary()
    assert usage.engines[0].engine == "bhashini" and usage.engines[0].calls == 2


async def test_bhashini_retries_a_server_error_but_not_a_refusal(
    bhashini_on: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(bhashini_module.asyncio, "sleep", _no_sleep)
    transport, seen = _bhashini_server(failures=2)
    assert await Bhashini(transport).translate(["नमस्ते"], LANGUAGES["hi"], ENGLISH) == ["B:नमस्ते"]
    assert seen.count("compute") == 3

    transport, seen = _bhashini_server(refuse=True)
    with pytest.raises(BhashiniError, match="refused"):
        await Bhashini(transport).translate(["नमस्ते"], LANGUAGES["hi"], ENGLISH)
    assert seen.count("compute") == 1


async def _no_sleep(_: float) -> None:
    return None


async def test_a_bhashini_failure_falls_back_and_only_the_engine_changes(
    bhashini_on: None, engine: FakeEngine, monkeypatch: pytest.MonkeyPatch
) -> None:
    governance.save_policy(governance.Policy(bhashini="internal"))
    monkeypatch.setattr(bhashini_module.asyncio, "sleep", _no_sleep)
    transport, _ = _bhashini_server(refuse=True)
    monkeypatch.setattr(language, "get_bhashini", lambda: Bhashini(transport))
    monkeypatch.setattr(language, "_open_source", engine.translate)

    result = await language.translate(
        ["नमस्ते"], LANGUAGES["hi"], ENGLISH, sensitivity=EvidenceClassification.INTERNAL
    )
    assert result.engine == "indictrans2" and result.fallback
    assert result.lines == ["EN(hi) नमस्ते"]

    confidential = await language.translate(
        ["नमस्ते"], LANGUAGES["hi"], ENGLISH, sensitivity=EvidenceClassification.CONFIDENTIAL
    )
    assert confidential.engine == "indictrans2" and not confidential.fallback
    assert confidential.lines == result.lines
    assert any(e.fallbacks == 1 for e in usage_summary().engines)


# --- the viewer's originals ----------------------------------------------------------------------


async def test_a_run_serves_each_translated_document_with_its_original() -> None:
    reset_registry()
    record = MissionRecord("run-lang", Objective(text="Did M3 agree?"), ["report_hi.txt"])
    record.texts = {"report_hi.txt": "[translated:hi] Work completed on 15 May 2026."}
    record.languages = {
        "report_hi.txt": DocumentLanguage(
            language="hi",
            language_name="Hindi",
            engine="indictrans2",
            engine_version="v",
            original_text="कार्य 15 मई 2026 को पूरा हुआ।",
            translated_lines=[1],
        )
    }
    get_registry()._missions[record.run_id] = record
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=create_app()), base_url="http://t"
    ) as client:
        body = (await client.get("/api/v1/missions/run-lang/originals")).json()
    assert body["report_hi.txt"]["original_text"].startswith("कार्य")
    assert body["report_hi.txt"]["translated_lines"] == [1]
