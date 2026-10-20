"""Benchmark against the plain model and frontier models (Phase B1).

The same scenarios, the same files and the same question go to every system; every answer is
scored against a written answer key (`.agent/evals/benchmark/answers.yaml`) by the same
deterministic judge. No model grades any answer.

Systems:
- **jarvis** - the full pipeline, through the same `run_scenario` the evaluation harness uses.
- **plain** - the same local model in one prompt: the files with numbered lines, the question, and
  an instruction to cite `[file:line]`. Numbered lines and the citation instruction help the plain
  model; the comparison is meant to be fair to it.
- **frontier** - the same prompt to a cloud model, only when its API key is set and named in
  `BENCH_FRONTIER` (e.g. `openai:gpt-4o,anthropic:claude-sonnet-4-5`). Benchmark fixtures are
  synthetic, so sending them is safe; real case files never take this path. Without a key the system
  is reported as skipped, with the reason.

Metrics, named after the methods they follow:
- **correct** - share of the answer key's facts the answer states (recall of known answers).
- **factscore** - FActScore-style precision: share of the answer's atomic sentences supported by a
  line in the supplied files (Member 4's lexical checker, the one every report already uses).
- **invented** - dates and figures the answer states that no file contains.
- **citation precision** - ALCE-style: share of citations whose cited line is relevant to the claim
  it is attached to. Citations that point nowhere (no such file or line) count as imprecise.
- **false alarms** - on negative scenarios, an answer that raises an alarm (a contradiction,
  compromise, mismatch...) without negating it; on the injection scenario, repeating the
  injection's words.

    python -m app.evaluation.benchmark [--scenarios a,b] [--systems jarvis,plain]
"""

from __future__ import annotations

import argparse
import asyncio
import json
import re
import time
from collections.abc import Awaitable, Callable
from datetime import datetime
from pathlib import Path

import yaml
from pydantic import Field

from app.core.config import get_settings
from app.core.logging import get_logger
from app.evaluation.metrics import ScenarioExpectation
from app.evaluation.runner import _resolve, load_expectations, run_scenario
from app.intelligence.proof import answer_of, evidence_lines
from app.intelligence.synthesis.grounding import check_narrative
from app.intelligence.trust.answer import split_into_claims
from app.intelligence.trust.lexical import verify_claim
from app.llm import frontier, get_provider
from app.llm.errors import LLMError
from app.llm.provider import CompletionRequest
from app.schemas.common import JarvisModel, SourceLocator, utcnow
from app.schemas.result import SectionKind
from app.schemas.trust import EvidenceText, TrustStatus
from app.tools.formats import prepare
from app.tools.loader import load_documents

log = get_logger(__name__)

PROMPT_VERSION = 1
_PROMPT = """You are given documents and a question. Answer the question using only the documents.
Every line of every document is numbered. After each statement, cite the line or lines it rests on
as [file:line], for example [report.txt:12]. State the dates, figures and names that matter. If the
documents show nothing of what the question asks about, say so plainly.

{documents}

Question: {question}

Reply as JSON: {{"answer": "<the answer, one paragraph, with [file:line] citations>"}}"""
MAX_PROMPT_CHARS = 24_000

_CITE = re.compile(r"\[([^\[\]:]+?):(\d+)\]")
_ALARM = re.compile(
    r"contradict|inconsisten|discrepan|conflict|mismatch|disagree|malicious|compromis|attack"
    r"|suspicious|overrun|exceed|unauthori[sz]ed|fraud",
    re.IGNORECASE,
)
_NEGATED = re.compile(
    r"\b(no|not|none|never|without|nothing|neither|nor|consistent|agree|agrees|match|matches)\b",
    re.IGNORECASE,
)


# --- the answer key and the judge ----------------------------------------------------------------


class AnswerKey(JarvisModel):
    facts: list[list[str]] = Field(default_factory=list)
    negative: bool = False
    forbidden: list[str] = Field(default_factory=list)


def benchmark_dir() -> Path:
    return get_settings().agent_dir / "evals" / "benchmark"


def load_answer_key(path: Path | None = None) -> dict[str, AnswerKey]:
    raw = yaml.safe_load((path or benchmark_dir() / "answers.yaml").read_text(encoding="utf-8"))
    return {sid: AnswerKey.model_validate(body or {}) for sid, body in (raw or {}).items()}


class Claim(JarvisModel):
    """One statement of an answer, and the places it cites as (document, 1-based line)."""

    text: str
    cites: list[tuple[str, int]] = Field(default_factory=list)


def facts_found(text: str, key: AnswerKey) -> int:
    lowered = f" {text.lower()} "
    return sum(1 for group in key.facts if any(p.lower() in lowered for p in group))


def raises_alarm(sentence: str) -> bool:
    """An alarm word with nothing negating it: "the reports contradict" is an alarm, "no
    contradiction was found" and "the figures are consistent" are not."""
    return bool(_ALARM.search(sentence)) and not _NEGATED.search(sentence)


def cited_line(texts: dict[str, str], document: str, line: int) -> str | None:
    text = texts.get(document)
    if text is None:
        return None
    lines = text.splitlines()
    return lines[line - 1] if 1 <= line <= len(lines) and lines[line - 1].strip() else None


class ScenarioScore(JarvisModel):
    scenario_id: str
    system: str
    claims: int = 0
    correct: float | None = None
    supported: int = 0
    sentences: int = 0
    invented: list[str] = Field(default_factory=list)
    citations: int = 0
    citations_precise: int = 0
    false_alarm: bool | None = None
    latency_ms: int = 0
    error: str = ""
    answer: str = ""


def score(
    scenario_id: str,
    system: str,
    claims: list[Claim],
    key: AnswerKey,
    texts: dict[str, str],
    *,
    latency_ms: int = 0,
    error: str = "",
) -> ScenarioScore:
    pool = evidence_lines(texts)
    whole = " ".join(c.text for c in claims)
    result = ScenarioScore(
        scenario_id=scenario_id,
        system=system,
        claims=len(claims),
        latency_ms=latency_ms,
        error=error,
        answer=whole[:2000],
    )
    if key.facts:
        result.correct = facts_found(whole, key) / len(key.facts)
    for claim in claims:
        check = check_narrative(SectionKind.EXECUTIVE_SUMMARY, claim.text, pool)
        if check is None:
            continue
        for s in check.sentences:
            result.sentences += 1
            result.supported += s.status is TrustStatus.SUPPORTED
            result.invented.extend(v for v in s.ungrounded if v not in result.invented)
        for document, line in claim.cites:
            result.citations += 1
            text = cited_line(texts, document, line)
            if text is None:
                continue
            verdict = verify_claim(
                claim.text, [EvidenceText(source=f"{document}:{line}", content=text)]
            )
            result.citations_precise += bool(verdict.scored and verdict.scored[0].relevant)
    if key.negative:
        result.false_alarm = any(raises_alarm(s) for c in claims for s in split_into_claims(c.text))
    elif key.forbidden:
        result.false_alarm = any(f.lower() in whole.lower() for f in key.forbidden)
    return result


# --- the systems ---------------------------------------------------------------------------------


def numbered(texts: dict[str, str]) -> tuple[str, bool]:
    parts: list[str] = []
    used, truncated = 0, False
    for name, text in sorted(texts.items()):
        body = "\n".join(f"{n}| {line}" for n, line in enumerate(text.splitlines(), start=1))
        room = MAX_PROMPT_CHARS - used
        if room <= 0:
            truncated = True
            break
        truncated = truncated or len(body) > room
        body = body[:room]
        used += len(body)
        parts.append(f"=== {name} ===\n{body}")
    return "\n\n".join(parts), truncated


def claims_from_answer(answer: str) -> list[Claim]:
    out: list[Claim] = []
    for sentence in split_into_claims(answer):
        cites = [(d.strip(), int(n)) for d, n in _CITE.findall(sentence)]
        text = _CITE.sub("", sentence).strip()
        if text:
            out.append(Claim(text=text, cites=cites))
    return out


def _line_of(loc: SourceLocator, texts: dict[str, str]) -> int | None:
    text = texts.get(loc.document_name) or texts.get(loc.document_id)
    if loc.row is not None:
        return loc.row
    if loc.char_start is not None and text is not None:
        return text.count("\n", 0, loc.char_start) + 1
    return None


Ask = Callable[[str], Awaitable[tuple[str, int]]]


async def _ask_local(prompt: str) -> tuple[str, int]:
    response = await get_provider().complete(
        CompletionRequest(prompt=prompt, role="baseline", max_tokens=1200, json_mode=True)
    )
    return answer_of(response.text), response.latency_ms


def _frontier(spec: str) -> tuple[Ask | None, str]:
    """An `Ask` for `provider:model`, or None and why not (the HTTP is in app/llm/frontier.py)."""
    provider, _, model = spec.partition(":")
    settings = get_settings()
    if provider == "openai":
        if not settings.openai_api_key:
            return None, "OPENAI_API_KEY is not set"

        async def ask_openai(prompt: str) -> tuple[str, int]:
            text, ms = await frontier.openai_chat(
                prompt, model, settings.openai_api_key, settings.openai_base_url
            )
            return answer_of(text), ms

        return ask_openai, ""
    if provider == "anthropic":
        if not settings.anthropic_api_key:
            return None, "ANTHROPIC_API_KEY is not set"

        async def ask_anthropic(prompt: str) -> tuple[str, int]:
            text, ms = await frontier.anthropic_messages(prompt, model, settings.anthropic_api_key)
            return answer_of(text), ms

        return ask_anthropic, ""
    return None, f"unknown provider '{provider}' (openai or anthropic)"


# --- the run -------------------------------------------------------------------------------------


class SystemSummary(JarvisModel):
    system: str
    scenarios: int
    correct: float | None = None
    factscore: float | None = None
    invented: int = 0
    citation_precision: float | None = None
    citations: int = 0
    false_alarms: int = 0
    alarm_cases: int = 0
    mean_latency_s: float = 0.0
    errors: int = 0


class BenchmarkReport(JarvisModel):
    generated_at: datetime = Field(default_factory=utcnow)
    model: str
    prompt_version: int = PROMPT_VERSION
    method: str = (
        "Same files and question to every system; scored against "
        ".agent/evals/benchmark/answers.yaml by a deterministic judge (no model grades any "
        "answer). correct = share of key facts stated; factscore = share of sentences supported "
        "by a line of the files (FActScore-style); invented = dates and figures in no file; "
        "citation precision = share of citations whose line is relevant to the claim "
        "(ALCE-style); false alarms on negative and injection scenarios."
    )
    systems: list[SystemSummary] = Field(default_factory=list)
    results: list[ScenarioScore] = Field(default_factory=list)
    skipped: dict[str, str] = Field(default_factory=dict)


def summarise(system: str, rows: list[ScenarioScore]) -> SystemSummary:
    def mean(values: list[float]) -> float | None:
        return round(sum(values) / len(values), 3) if values else None

    sentences = sum(r.sentences for r in rows)
    citations = sum(r.citations for r in rows)
    alarms = [r for r in rows if r.false_alarm is not None]
    return SystemSummary(
        system=system,
        scenarios=len(rows),
        correct=mean([r.correct for r in rows if r.correct is not None]),
        factscore=round(sum(r.supported for r in rows) / sentences, 3) if sentences else None,
        invented=sum(len(r.invented) for r in rows),
        citation_precision=round(sum(r.citations_precise for r in rows) / citations, 3)
        if citations
        else None,
        citations=citations,
        false_alarms=sum(1 for r in alarms if r.false_alarm),
        alarm_cases=len(alarms),
        mean_latency_s=round(sum(r.latency_ms for r in rows) / 1000 / max(len(rows), 1), 1),
        errors=sum(1 for r in rows if r.error),
    )


async def _texts_for(expectation: ScenarioExpectation) -> dict[str, str]:
    paths = [_resolve(d) for d in expectation.documents]
    await prepare(paths, get_provider())
    texts, _ = load_documents(paths)
    return texts


async def run_benchmark(
    scenario_ids: list[str] | None = None, systems: list[str] | None = None
) -> BenchmarkReport:
    keys = load_answer_key()
    expectations = [
        e
        for e in load_expectations("all")
        if e.scenario_id in keys and (not scenario_ids or e.scenario_id in scenario_ids)
    ]
    wanted = systems or ["jarvis", "plain"]
    report = BenchmarkReport(model=get_provider().model_id)

    asks: dict[str, Ask] = {}
    if "plain" in wanted:
        asks["plain"] = _ask_local
    specs = [x.strip() for x in get_settings().bench_frontier.split(",") if x.strip()]
    for spec in specs:
        ask, why = _frontier(spec)
        if ask is None:
            report.skipped[spec] = why
        else:
            asks[spec] = ask
    if not specs:
        report.skipped["frontier models"] = (
            "none configured: set JARVIS_BENCH_FRONTIER (e.g. openai:gpt-4o) and its API key"
        )

    for expectation in expectations:
        key = keys[expectation.scenario_id]
        texts = await _texts_for(expectation)
        log.info("benchmark_scenario", scenario=expectation.scenario_id)
        if "jarvis" in wanted:
            started = time.perf_counter()
            outcome = await run_scenario(expectation)
            claims = [
                Claim(
                    text=f.claim,
                    cites=[
                        (e.locator.document_name or e.locator.document_id, line)
                        for e in f.evidence
                        if (line := _line_of(e.locator, texts)) is not None
                    ],
                )
                for f in outcome.findings
            ]
            report.results.append(
                score(
                    expectation.scenario_id,
                    "jarvis",
                    claims,
                    key,
                    texts,
                    latency_ms=int((time.perf_counter() - started) * 1000),
                    error=outcome.error,
                )
            )
        documents, _ = numbered(texts)
        prompt = _PROMPT.format(documents=documents, question=expectation.objective)
        for name, ask in asks.items():
            try:
                answer, latency = await ask(prompt)
                report.results.append(
                    score(
                        expectation.scenario_id,
                        name,
                        claims_from_answer(answer),
                        key,
                        texts,
                        latency_ms=latency,
                    )
                )
            # One system failing must not lose the others' results.
            except (frontier.FrontierError, KeyError, ValueError, LLMError) as exc:
                log.warning("benchmark_system_failed", system=name, error=str(exc))
                report.results.append(
                    score(expectation.scenario_id, name, [], key, texts, error=type(exc).__name__)
                )

    names = [n for n in ["jarvis", *asks] if any(r.system == n for r in report.results)]
    report.systems = [summarise(n, [r for r in report.results if r.system == n]) for n in names]
    return report


def write_report(report: BenchmarkReport) -> Path:
    directory = benchmark_dir() / "reports"
    directory.mkdir(parents=True, exist_ok=True)
    stamp = report.generated_at.strftime("%Y%m%dT%H%M%S")
    path = directory / f"{stamp}-benchmark.json"
    path.write_text(report.model_dump_json(indent=2), encoding="utf-8")
    lines = [
        f"# Benchmark {stamp}",
        "",
        f"Model: `{report.model}` · {report.method}",
        "",
        "| System | Correct | FActScore | Invented | Citation precision | False alarms | Latency |",
        "|---|---|---|---|---|---|---|",
    ]
    for s in report.systems:
        lines.append(
            f"| {s.system} | {s.correct} | {s.factscore} | {s.invented} | "
            f"{s.citation_precision} ({s.citations}) | {s.false_alarms}/{s.alarm_cases} | "
            f"{s.mean_latency_s} s |"
        )
    for name, why in report.skipped.items():
        lines.append(f"\nSkipped: {name} - {why}")
    path.with_suffix(".md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


def newest_report() -> BenchmarkReport | None:
    directory = benchmark_dir() / "reports"
    files = sorted(directory.glob("*-benchmark.json")) if directory.is_dir() else []
    if not files:
        return None
    return BenchmarkReport.model_validate(json.loads(files[-1].read_text(encoding="utf-8")))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0] if __doc__ else "")
    parser.add_argument("--scenarios", default="")
    parser.add_argument("--systems", default="jarvis,plain")
    args = parser.parse_args()
    report = asyncio.run(
        run_benchmark(
            [s for s in args.scenarios.split(",") if s] or None,
            [s for s in args.systems.split(",") if s],
        )
    )
    print(write_report(report))  # noqa: T201
    for s in report.systems:
        print(s.model_dump_json())  # noqa: T201


if __name__ == "__main__":
    main()
