"""The trust benchmark: Member 4's verifier evaluation, ported into the harness (Phase 26).

Ported from `Mem-4/eval/generate_benchmark.py` and `run_benchmark.py`.

**The generator** builds a synthetic incident-investigation corpus from 40 base facts (a person,
company, location, clock time, shipment id and amount each). Every fact gets one evidence
document; a random 20% get a verbatim duplicate; a random 25% get a second copy with the hour
shifted by 1-3, which is the planted contradiction. Cases are one claim per fact, expected
`CONTRADICTED` if it was conflicted and `SUPPORTED` otherwise, plus 20 `INSUFFICIENT_EVIDENCE`
cases about shipments and people that do not exist. A risky case is one expected `CONTRADICTED` or
`INSUFFICIENT_EVIDENCE`. With the same seed (42) it produces
**byte-identical data** to the original, which a test checks against the committed files.

**The runner** verifies every case against the whole corpus and reports Member 4's metrics:

| Metric | Definition |
|---|---|
| `accuracy` | share of cases whose status matches the expected one |
| `hallucination_rate` | share of risky cases marked `SUPPORTED` (false confidence) |
| `category_accuracy` | accuracy per category: supported, contradiction, insufficient_evidence |
| `avg_latency_ms` | mean verification time per case |

What changed from the original: the report is a typed model, stamped with the thresholds and a
hash of the data so two reports can only be compared when they measured the same thing, and it is
written to `.agent/evals/trust/reports/` like the agent reports. The original also logged every
case to episodic memory; that returns with memory in Phase 33.

**What this benchmark does and does not show.** It was generated to exercise exactly the conflict
rule the verifier implements: clock times on a shared shipment id. A perfect score shows the code
does what it says. It does not show that the rule generalises. That is what the shipment
scenarios in the mission suite are for (Phase 34).
"""

from __future__ import annotations

import hashlib
import json
import random
import time
from collections import Counter
from datetime import datetime
from pathlib import Path

from pydantic import Field

from app.core.agent_config import get_lexical_thresholds
from app.core.config import get_settings
from app.evaluation.security import SecurityReport, run_security_suite
from app.intelligence.trust.lexical import verify_claim
from app.schemas.common import JarvisModel, UnitFloat, utcnow
from app.schemas.trust import EvidenceText, LexicalThresholds, TrustStatus

# The original's fixed vocabularies, unchanged. Order matters: the generator draws from them by
# position, and reordering would change every generated case.
PEOPLE = ["Rahul Sharma", "Priya Nair", "Aman Verma", "Sana Iyer", "Devika Rao", "Karan Mehta"]
COMPANIES = ["ABC Logistics", "Orion Freight", "Zenith Traders", "Meridian Supply Co"]
LOCATIONS = ["Mumbai Facility", "Pune Warehouse B", "Navi Mumbai Depot", "Thane Loading Dock"]
DOC_TYPES = [
    "incident_report",
    "employee_statement",
    "security_report",
    "invoice",
    "shipping_report",
    "inspection_log",
    "transactions",
    "audit_note",
]
SEED = 42

RISKY = {TrustStatus.CONTRADICTED.value, TrustStatus.INSUFFICIENT_EVIDENCE.value}


def trust_dir() -> Path:
    return get_settings().agent_dir / "evals" / "trust"


# --- generator -------------------------------------------------------------------


def _doc_name(i: int) -> str:
    return f"{DOC_TYPES[i % len(DOC_TYPES)]}_{i:03d}.pdf"


def generate(
    n_facts: int = 40, n_insufficient: int = 20, seed: int = SEED
) -> tuple[list[dict[str, object]], list[dict[str, object]]]:
    """The evidence corpus and the benchmark cases, exactly as the original produced them.

    The original seeded the module-level `random` and drew in a fixed order: the facts, the
    contradiction and duplicate samples, the alternative times, then one shuffle. A private
    `Random(seed)` drawing in the same order reproduces it without touching global state.
    """
    # Not cryptographic. A seeded generator is the point: the same data every time.
    rng = random.Random(seed)  # noqa: S311

    facts: list[dict[str, object]] = []
    for i in range(n_facts):
        person = rng.choice(PEOPLE)
        company = rng.choice(COMPANIES)
        location = rng.choice(LOCATIONS)
        hour = rng.randint(6, 20)
        minute = rng.choice([0, 15, 30, 40, 45])
        amount = rng.choice([4821, 5620, 7300, 9150, 12040, 15600])
        facts.append(
            {
                "fact_id": f"F{i:03d}",
                "person": person,
                "company": company,
                "location": location,
                "time": f"{hour}:{minute:02d} {'AM' if hour < 12 else 'PM'}",
                "shipment_id": 1000 + i,
                "amount": amount,
            }
        )

    corpus: list[dict[str, object]] = []
    counter = 0
    contradicted = set(rng.sample(range(n_facts), k=n_facts // 4))
    duplicated = set(rng.sample(range(n_facts), k=n_facts // 5))

    for idx, fact in enumerate(facts):
        content = (
            f"{fact['person']} was present at {fact['location']} representing "
            f"{fact['company']}. Shipment {fact['shipment_id']} (amount {fact['amount']}) "
            f"was processed at {fact['time']}."
        )
        corpus.append(
            {
                "source": _doc_name(counter),
                "page": 1,
                "content": content,
                "fact_id": fact["fact_id"],
            }
        )
        counter += 1

        if idx in duplicated:
            corpus.append(
                {
                    "source": _doc_name(counter),
                    "page": 1,
                    "content": content,
                    "fact_id": fact["fact_id"],
                }
            )
            counter += 1

        if idx in contradicted:
            hour = int(str(fact["time"]).split(":")[0])
            alt_hour = (hour + rng.choice([1, 2, 3])) % 24
            alt_time = (
                f"{alt_hour}:{rng.choice(['00', '15', '30'])} {'AM' if alt_hour < 12 else 'PM'}"
            )
            conflict = (
                f"{fact['person']} was present at {fact['location']} representing "
                f"{fact['company']}. Shipment {fact['shipment_id']} (amount {fact['amount']}) "
                f"was processed at {alt_time}."
            )
            corpus.append(
                {
                    "source": _doc_name(counter),
                    "page": 1,
                    "content": conflict,
                    "fact_id": fact["fact_id"],
                    "conflict": True,
                }
            )
            counter += 1

    cases: list[dict[str, object]] = []
    for idx, fact in enumerate(facts):
        expected = "CONTRADICTED" if idx in contradicted else "SUPPORTED"
        cases.append(
            {
                "case_id": f"BENCH-{idx:03d}",
                "question": f"When was shipment {fact['shipment_id']} processed and by whom?",
                "claim_text": (
                    f"Shipment {fact['shipment_id']} was processed at {fact['time']} "
                    f"by {fact['person']} representing {fact['company']}."
                ),
                "expected_status": expected,
                "category": "contradiction" if expected == "CONTRADICTED" else "supported",
            }
        )
    for i in range(n_insufficient):
        cases.append(
            {
                "case_id": f"BENCH-INSUFF-{i:03d}",
                "question": (
                    f"What was the salary of Unlisted Person {i} in shipment {90000 + i}?"
                ),
                "claim_text": (
                    f"Unlisted Person {i} received a salary related to shipment {90000 + i}."
                ),
                "expected_status": "INSUFFICIENT_EVIDENCE",
                "category": "insufficient_evidence",
            }
        )
    rng.shuffle(cases)
    return corpus, cases


# --- report ----------------------------------------------------------------------


class TrustCaseResult(JarvisModel):
    case_id: str
    category: str
    claim: str
    expected: str
    actual: str
    correct: bool
    relevance: UnitFloat = 0.0
    reasoning: str = ""


class TrustReport(JarvisModel):
    """One run of the trust benchmark. Every figure is computed from the cases below it."""

    generated_at: datetime = Field(default_factory=utcnow)
    verifier: str = "lexical"
    thresholds: LexicalThresholds
    # A digest of the corpus and cases, so two reports are comparable only on the same data.
    dataset_hash: str
    cases: int
    correct: int
    accuracy: UnitFloat
    hallucination_rate: UnitFloat
    risky_cases: int
    false_confidence: int
    category_accuracy: dict[str, float] = Field(default_factory=dict)
    avg_latency_ms: float = Field(ge=0.0)
    # Member 4's injection detection rate, from the security suite run alongside (Phase 27).
    injection_detection_rate: UnitFloat | None = None
    security: SecurityReport | None = None
    results: list[TrustCaseResult] = Field(default_factory=list)

    @property
    def failures(self) -> list[TrustCaseResult]:
        return [r for r in self.results if not r.correct]


def load_dataset(directory: Path | None = None) -> tuple[list[EvidenceText], list[dict[str, str]]]:
    base = directory or trust_dir()
    raw_corpus = json.loads((base / "evidence_corpus.json").read_text(encoding="utf-8"))
    cases = json.loads((base / "benchmark.json").read_text(encoding="utf-8"))
    corpus = [
        EvidenceText(source=f"{item['source']}:p{item['page']}", content=item["content"])
        for item in raw_corpus
    ]
    return corpus, cases


def dataset_hash(directory: Path | None = None) -> str:
    base = directory or trust_dir()
    digest = hashlib.sha256()
    for name in ("evidence_corpus.json", "benchmark.json"):
        digest.update((base / name).read_bytes())
    return "sha256:" + digest.hexdigest()[:16]


def run_trust_benchmark(
    thresholds: LexicalThresholds | None = None, directory: Path | None = None
) -> TrustReport:
    """Verify every case against the whole corpus, exactly as the original runner did."""
    limits = thresholds or get_lexical_thresholds()
    corpus, cases = load_dataset(directory)

    results: list[TrustCaseResult] = []
    latencies: list[float] = []
    for case in cases:
        started = time.perf_counter()
        verdict = verify_claim(case["claim_text"], corpus, limits)
        latencies.append((time.perf_counter() - started) * 1000)
        results.append(
            TrustCaseResult(
                case_id=case["case_id"],
                category=case["category"],
                claim=case["claim_text"],
                expected=case["expected_status"],
                actual=verdict.status.value,
                correct=verdict.status.value == case["expected_status"],
                relevance=verdict.relevance_score,
                reasoning=verdict.reasoning,
            )
        )

    risky = [r for r in results if r.expected in RISKY]
    false_confidence = [r for r in risky if r.actual == TrustStatus.SUPPORTED.value]
    totals = Counter(r.category for r in results)
    correct = Counter(r.category for r in results if r.correct)

    security = run_security_suite()

    return TrustReport(
        injection_detection_rate=security.detection_rate,
        security=security,
        thresholds=limits,
        dataset_hash=dataset_hash(directory),
        cases=len(results),
        correct=sum(r.correct for r in results),
        accuracy=sum(r.correct for r in results) / len(results) if results else 0.0,
        hallucination_rate=len(false_confidence) / len(risky) if risky else 0.0,
        risky_cases=len(risky),
        false_confidence=len(false_confidence),
        category_accuracy={c: correct[c] / totals[c] for c in sorted(totals)},
        avg_latency_ms=sum(latencies) / len(latencies) if latencies else 0.0,
        results=results,
    )


def render_markdown(report: TrustReport) -> str:
    lines = [
        "# JARVIS Trust Benchmark",
        "",
        f"**Verifier:** {report.verifier}  ",
        f"**Generated:** {report.generated_at:%Y-%m-%d %H:%M} UTC  ",
        f"**Dataset:** `{report.dataset_hash}`  ",
        f"**Thresholds:** relevance {report.thresholds.relevance}, "
        f"support {report.thresholds.support}, conflict {report.thresholds.conflict}",
        "",
        "Ported from Member 4's `eval/run_benchmark.py`. Every figure is computed from the cases.",
        "",
        "| Metric | Value |",
        "|---|---|",
        f"| accuracy | {report.accuracy:.3f} ({report.correct}/{report.cases}) |",
        f"| hallucination_rate | {report.hallucination_rate:.3f} "
        f"({report.false_confidence}/{report.risky_cases} risky cases) |",
        f"| avg_latency_ms | {report.avg_latency_ms:.2f} |",
    ]
    if report.injection_detection_rate is not None:
        lines.append(f"| injection_detection_rate | {report.injection_detection_rate:.3f} |")
    if report.security is not None:
        lines += [
            f"| injection attack_recall | {report.security.attack_recall:.3f} |",
            f"| injection false_positive_rate | {report.security.false_positive_rate:.3f} |",
        ]
    lines += ["", "| Category | Accuracy |", "|---|---|"]
    lines += [f"| {c} | {a:.3f} |" for c, a in report.category_accuracy.items()]
    if report.security is not None and report.security.failures:
        lines += ["", "## Security suite failures", ""]
        lines += [
            f"- `{r.id}` ({r.source}) expected flag={r.expected_flag}, got {r.categories or 'none'}"
            for r in report.security.failures
        ]
    if report.failures:
        lines += ["", "## Failures", ""]
        lines += [
            f"- `{r.case_id}` expected {r.expected}, got {r.actual}: {r.claim}"
            for r in report.failures
        ]
    return "\n".join(lines) + "\n"


def write_trust_report(report: TrustReport, directory: Path | None = None) -> tuple[Path, Path]:
    out = (directory or trust_dir()) / "reports"
    out.mkdir(parents=True, exist_ok=True)
    stem = f"{report.generated_at:%Y%m%dT%H%M%S}-{report.verifier}"
    json_path, md_path = out / f"{stem}.json", out / f"{stem}.md"
    json_path.write_text(report.model_dump_json(indent=2), encoding="utf-8")
    md_path.write_text(render_markdown(report), encoding="utf-8")
    return json_path, md_path
