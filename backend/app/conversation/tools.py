"""The conversation's tools and the case material they read (v4 Phase 3).

Six tools, each deterministic and bounded, each returning text the model reads and the turn records:

- `search_evidence(query)` - the case's lines that share the query's words, best first (BM25), each
  after its locator;
- `read_span(document, start, end)` - consecutive lines of one document, at most 40;
- `query_findings(text)` - the case's findings whose claim shares the text's words, with id, status
  and evidence (the plan's `query_graph`: the findings are the case's verified graph of claims);
- `calculate(expression)` - arithmetic, parsed and whitelisted (`safe_eval`), never `eval`;
- `compare_values(a, b)` - two dates or two figures: equal, or which is larger and by how much;
- `ask_user(question)` - stops the loop; the question goes to the person.

`verify_claim` is not a tool the model may skip: every claim of the answer is verified by the
service after the loop, whatever the model chose to call.
"""

from __future__ import annotations

from typing import Any

from pydantic import Field

from app.api.registry import get_registry
from app.cases.service import get_case_store
from app.core.logging import get_logger
from app.evidence.service import get_locker
from app.intelligence.context.hybrid import terms
from app.intelligence.temporal import find_dates, find_figures, parse_number
from app.schemas.common import JarvisModel
from app.schemas.finding import Finding
from app.schemas.language import DocumentLanguage
from app.tools.builtin import UnsafeExpressionError, safe_eval
from app.tools.loader import load_uploads

log = get_logger(__name__)

MAX_SPAN = 40
SEARCH_HITS = 8
TOOL_RESULT_CHARS = 2400


class CaseFinding(JarvisModel):
    run_id: str
    finding: Finding


class CaseMaterial(JarvisModel):
    """What a conversation about a case may read: its documents, line by line, and its findings."""

    case_id: str
    documents: dict[str, str] = Field(default_factory=dict)
    findings: list[CaseFinding] = Field(default_factory=list)
    # Locator -> the text the run that cited it read there (what verification compares against).
    evidence_text: dict[str, str] = Field(default_factory=dict)
    # Documents read through a translation, with their originals (v4 Phase 6).
    languages: dict[str, DocumentLanguage] = Field(default_factory=dict)
    # Each filed document's sensitivity, for routing language requests (v4 Phase 7).
    sensitivities: list[str] = Field(default_factory=list)

    def line(self, locator: str) -> str | None:
        document, _, position = locator.rpartition(":")
        if not position.startswith("r") or not position[1:].isdigit():
            return None
        lines = self.documents.get(document, "").splitlines()
        number = int(position[1:])
        if 1 <= number <= len(lines) and lines[number - 1].strip():
            return lines[number - 1].strip()
        return None

    def find(self, reference: str) -> CaseFinding | None:
        """`F-002`, or `run_x/F-002` when several runs have one: the newest run's by default."""
        run_id, _, finding_id = reference.rpartition("/")
        for item in reversed(self.findings):
            if item.finding.finding_id == finding_id and run_id in ("", item.run_id):
                return item
        return None


async def gather(case_id: str) -> CaseMaterial:
    """The case's material: the text its investigations read, the files filed in it, findings."""
    material = CaseMaterial(case_id=case_id)
    store = await get_case_store()
    registry = get_registry()
    for investigation in await store.investigations(case_id):
        record = registry.get(investigation.run_id)
        if record is None:
            continue
        material.documents.update(record.texts)
        material.languages.update(record.languages)
        if record.result is not None:
            material.evidence_text.update(record.result.evidence_text)
            material.findings.extend(
                CaseFinding(run_id=record.run_id, finding=f) for f in record.result.findings
            )
    try:
        locker = await get_locker()
        names = []
        for link in await store.evidence(case_id):
            item = await locker.get(link.evidence_id)
            if item is not None:
                material.sensitivities.append(item.classification.value)
            if item is not None and item.name not in material.documents:
                names.append(item.name)
        if names:
            texts, loaded = load_uploads(names)
            material.documents.update(texts)
            material.languages.update(
                {d.document_id: d.reading for d in loaded if d.reading is not None}
            )
    except Exception as exc:  # noqa: BLE001 - the runs' text is still there to read
        log.warning("case_evidence_unreadable", case_id=case_id, error=str(exc))
    return material


# --- the tools ---------------------------------------------------------------------------------


def _bounded(text: str) -> str:
    return text if len(text) <= TOOL_RESULT_CHARS else text[:TOOL_RESULT_CHARS] + "\n[...cut]"


def search_evidence(material: CaseMaterial, query: str) -> str:
    wanted = set(terms(query))
    if not wanted:
        return "no searchable words in the query"
    scored = []
    for document, text in sorted(material.documents.items()):
        for number, line in enumerate(text.splitlines(), start=1):
            words = set(terms(line))
            hits = len(wanted & words)
            if hits:
                scored.append((hits / len(wanted), f"[{document}:r{number}] {line.strip()}"))
    scored.sort(key=lambda pair: -pair[0])
    if not scored:
        return f"no line of the case's {len(material.documents)} document(s) shares those words"
    return _bounded("\n".join(text for _, text in scored[:SEARCH_HITS]))


def read_span(material: CaseMaterial, document: str, start: int, end: int) -> str:
    text = material.documents.get(document)
    if text is None:
        return f"no document {document!r}; the case holds: {', '.join(sorted(material.documents))}"
    lines = text.splitlines()
    start = max(1, start)
    end = min(len(lines), max(start, end), start + MAX_SPAN - 1)
    return _bounded(
        "\n".join(
            f"[{document}:r{n}] {lines[n - 1].strip()}"
            for n in range(start, end + 1)
            if lines[n - 1].strip()
        )
        or "those lines are empty"
    )


def query_findings(material: CaseMaterial, text: str) -> str:
    wanted = set(terms(text))
    rows = []
    for item in material.findings:
        finding = item.finding
        overlap = len(wanted & set(terms(finding.claim))) if wanted else 1
        if overlap:
            status = finding.verification.status.value if finding.verification else "UNVERIFIED"
            cites = ", ".join(r.as_ref() for r in finding.evidence if r.is_resolved)
            rows.append(
                (
                    overlap,
                    f"{item.run_id}/{finding.finding_id} [{status}] {finding.claim} ({cites})",
                )
            )
    rows.sort(key=lambda pair: -pair[0])
    return _bounded("\n".join(r for _, r in rows[:10]) or "no finding of this case matches")


def calculate(expression: str) -> str:
    try:
        value = safe_eval(expression.replace(",", ""))
    except (UnsafeExpressionError, ZeroDivisionError, SyntaxError, ValueError) as exc:
        return f"cannot calculate {expression!r}: {exc}"
    return f"{expression} = {value:,.2f}".rstrip("0").rstrip(".")


def compare_values(a: str, b: str) -> str:
    dates_a, dates_b = find_dates(a), find_dates(b)
    if dates_a and dates_b:
        first, second = dates_a[0][1], dates_b[0][1]
        if first.compatible(second):
            return f"{a} and {b} are the same date"
        return f"{a} and {b} are different dates"
    x, y = parse_number(a), parse_number(b)
    if x is None or y is None:
        figures_a, figures_b = find_figures(a), find_figures(b)
        x = figures_a[0][1] if figures_a else x
        y = figures_b[0][1] if figures_b else y
    if x is None or y is None:
        return f"cannot compare {a!r} and {b!r}: neither two dates nor two figures"
    if x == y:
        return f"{a} and {b} are equal"
    larger, smaller = (a, b) if x > y else (b, a)
    return f"{larger} is larger than {smaller} by {abs(x - y):,}"


TOOLS = {
    "search_evidence": "search_evidence(query): the case's lines sharing the query's words",
    "read_span": "read_span(document, start, end): lines start..end of one document (max 40)",
    "query_findings": "query_findings(text): the case's findings about the text, with status",
    "calculate": "calculate(expression): arithmetic, e.g. 287500 - 250000",
    "compare_values": "compare_values(a, b): two dates or two figures compared",
    "ask_user": "ask_user(question): ask the person something only they can answer; stops here",
}


def run_tool(material: CaseMaterial, tool: str, arguments: dict[str, Any]) -> str:
    """One tool call. Bad arguments are reported to the model as a result, never raised."""

    def arg(name: str, default: Any = "") -> Any:
        return arguments.get(name, default)

    try:
        if tool == "search_evidence":
            return search_evidence(material, str(arg("query")))
        if tool == "read_span":
            return read_span(
                material, str(arg("document")), int(arg("start", 1)), int(arg("end", 1))
            )
        if tool == "query_findings":
            return query_findings(material, str(arg("text")))
        if tool == "calculate":
            return calculate(str(arg("expression")))
        if tool == "compare_values":
            return compare_values(str(arg("a")), str(arg("b")))
    except (TypeError, ValueError) as exc:
        return f"bad arguments for {tool}: {exc}"
    return f"no tool {tool!r}; the tools are: {', '.join(TOOLS)}"
