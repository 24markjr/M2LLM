"""The investigation report as a designed document (v4 Phase 5).

One document, drawn three ways - on screen (HTML), as PDF and as DOCX (`render.py`) - so the copies
cannot say different things. It is built from the typed report (Phase 51) and adds nothing to it:
every word is a finding, a quote, a hash or a count the report already holds. What it adds is shape:

1. **Executive brief** - the risk with its reason, what was established, the numbers;
2. **Findings** - one table, each row with its status, severity, evidence strength and sources;
3. **Contradictions** - side by side, both sources quoted at the cited line;
4. **Timeline**, **gaps and next evidence**, **competing explanations**, **limitations**;
5. **Appendix** - the receipt (run, model, content and receipt hashes) and every file with its
   SHA-256, authority and integrity.

Tones name what a cell means (verified, partial, unsupported, high...); each renderer decides the
colour, and the word is always there too, so colour is never the only cue.
"""

from __future__ import annotations

from typing import Literal

from pydantic import Field

from app.packs import ReportWords
from app.schemas.common import JarvisModel
from app.schemas.investigation_report import InvestigationReport, ReportFinding

Tone = Literal[
    "", "verified", "partial", "unsupported", "critical", "high", "medium", "low", "muted"
]


class Cell(JarvisModel):
    text: str
    tone: Tone = ""


class Block(JarvisModel):
    kind: Literal["heading", "paragraph", "bullets", "table", "pair", "facts"]
    text: str = ""
    tone: Tone = ""
    items: list[str] = Field(default_factory=list)
    columns: list[str] = Field(default_factory=list)
    rows: list[list[Cell]] = Field(default_factory=list)
    # A contradiction: two sides, each a source and its quote, and the claim they disagree on.
    left: tuple[str, str] = ("", "")
    right: tuple[str, str] = ("", "")
    facts: list[tuple[str, str]] = Field(default_factory=list)


class ReportDocument(JarvisModel):
    title: str
    subtitle: str
    facts: list[tuple[str, str]] = Field(default_factory=list)
    blocks: list[Block] = Field(default_factory=list)
    footer: str = ""


_VERDICT_TONE: dict[str, Tone] = {
    "SUPPORTED": "verified",
    "PARTIALLY_SUPPORTED": "partial",
    "UNSUPPORTED": "unsupported",
    "CONTRADICTED": "unsupported",
}
_SEVERITY_TONE: dict[str, Tone] = {
    "CRITICAL": "critical",
    "HIGH": "high",
    "MEDIUM": "medium",
    "LOW": "low",
    "INFO": "muted",
}


def _verdict(text: str) -> str:
    return text.split(" ", 1)[0].upper().strip(";,")


def _strength(confidence: float) -> str:
    if confidence <= 0:
        return "none"
    if confidence >= 0.7:
        return "strong"
    if confidence >= 0.4:
        return "moderate"
    return "weak"


def _heading(text: str) -> Block:
    return Block(kind="heading", text=text)


def _finding_rows(findings: list[ReportFinding], standing: str) -> list[list[Cell]]:
    rows = []
    for f in findings:
        verdict = _verdict(f.verification)
        rows.append(
            [
                Cell(text=f.finding_id),
                Cell(text=f.claim),
                Cell(
                    text=f"{standing}\n{verdict.replace('_', ' ').lower()}",
                    tone=_VERDICT_TONE.get(verdict, "muted"),
                ),
                Cell(text=f.severity.value.lower(), tone=_SEVERITY_TONE.get(f.severity.value, "")),
                Cell(text=_strength(f.confidence)),
                Cell(text=", ".join(f.citations) or "none resolved"),
            ]
        )
    return rows


def _contradiction(f: ReportFinding) -> Block | None:
    quoted = [(c, q) for c, q in f.quotes.items() if q]
    if len(quoted) < 2:
        return None
    first = quoted[0]
    document = first[0].rsplit(":", 1)[0]
    # The other side from another document when there is one: a contradiction between two sources.
    second = next((q for q in quoted[1:] if q[0].rsplit(":", 1)[0] != document), quoted[1])
    return Block(kind="pair", text=f"{f.finding_id}: {f.claim}", left=first, right=second)


def build_document(report: InvestigationReport, words: ReportWords | None = None) -> ReportDocument:
    """The document; `words` - the title and section names - come from the domain pack."""
    words = words or ReportWords()
    every = [*report.established, *report.awaiting_review, *report.not_established]
    blocks: list[Block] = []

    # 1. The executive brief.
    blocks.append(_heading(words.brief))
    blocks.append(
        Block(
            kind="paragraph",
            text=f"Risk: {report.risk.value}. {report.risk_reason}",
            tone=_SEVERITY_TONE.get(report.risk.value, ""),
        )
    )
    blocks.append(
        Block(kind="bullets", items=report.executive_summary)
        if report.executive_summary
        else Block(kind="paragraph", text="Nothing was established that can stand on its own.")
    )
    blocks.append(
        Block(
            kind="facts",
            facts=[
                ("Established", str(len(report.established))),
                ("Awaiting review", str(len(report.awaiting_review))),
                ("Not established", str(len(report.not_established))),
                ("Documents examined", str(len(report.evidence))),
            ],
        )
    )

    # 2. The findings matrix.
    blocks.append(_heading(words.findings))
    if every:
        blocks.append(
            Block(
                kind="table",
                columns=["ID", "Finding", "Status", "Severity", "Evidence", "Sources"],
                rows=[
                    *_finding_rows(report.established, "established"),
                    *_finding_rows(report.awaiting_review, "awaiting review"),
                    *_finding_rows(report.not_established, "not established"),
                ],
            )
        )
    else:
        blocks.append(Block(kind="paragraph", text="The investigation produced no findings."))

    # 3. Contradictions, both sides quoted.
    pairs = [
        b
        for f in every
        if f.statement.upper() == "CONTRADICTION" and (b := _contradiction(f)) is not None
    ]
    if pairs or report.contradictions:
        blocks.append(_heading(words.contradictions))
        blocks += pairs or [Block(kind="bullets", items=report.contradictions)]

    # 4. Timeline, gaps and next evidence, explanations, limitations.
    if report.timeline:
        blocks.append(_heading("Timeline"))
        blocks.append(
            Block(
                kind="table",
                columns=["Date", "Event", "Source"],
                rows=[
                    [Cell(text=t.date), Cell(text=t.event), Cell(text=t.source)]
                    for t in report.timeline
                ],
            )
        )
    if report.unknowns or report.recommendations:
        blocks.append(_heading(words.gaps))
        if report.unknowns:
            blocks.append(Block(kind="bullets", items=report.unknowns))
        if report.recommendations:
            blocks.append(Block(kind="paragraph", text="Recommended next steps:"))
            blocks.append(Block(kind="bullets", items=report.recommendations))
    if report.hypotheses:
        blocks.append(_heading("Competing explanations"))
        blocks.append(Block(kind="bullets", items=report.hypotheses))
    if report.limitations:
        blocks.append(_heading("Limitations"))
        blocks.append(Block(kind="bullets", items=report.limitations))

    # 5. The appendix: the receipt and the files.
    blocks.append(_heading("Appendix A - Receipt"))
    blocks.append(
        Block(
            kind="facts",
            facts=[
                ("Report", report.report_id),
                ("Run", report.run_id),
                ("Model", report.model or "-"),
                ("Generated", f"{report.generated_at:%d %B %Y, %H:%M UTC}"),
                ("Content hash", report.content_hash or "-"),
                ("Receipt hash", report.receipt_hash or "-"),
            ],
        )
    )
    blocks.append(_heading("Appendix B - Evidence and file hashes"))
    blocks.append(
        Block(
            kind="table",
            columns=["Document", "Evidence", "SHA-256", "Authority", "Integrity", "Cited by"],
            rows=[
                [
                    Cell(text=e.document),
                    Cell(
                        text=e.evidence_id or "not in the locker",
                        tone="" if e.evidence_id else "muted",
                    ),
                    # In full, in four groups so it wraps: one 64-character word fits no column.
                    Cell(text=" ".join(e.sha256[i : i + 16] for i in range(0, 64, 16)) or "-"),
                    Cell(text=e.authority.lower() or "-"),
                    Cell(
                        text=e.integrity.lower() or "-",
                        tone="verified" if e.integrity == "VERIFIED" else "",
                    ),
                    Cell(text=", ".join(e.cited_by) or "-"),
                ]
                for e in report.evidence
            ],
        )
        if report.evidence
        else Block(kind="paragraph", text="No evidence items.")
    )
    if report.narrative:
        blocks.append(_heading("Appendix C - Narrative (model-written, each sentence checked)"))
        blocks.append(Block(kind="bullets", items=report.narrative))

    facts = [("Objective", report.objective)]
    if report.case_id:
        facts.append(("Case", report.case_id))
    facts += [("Report", report.report_id), ("Generated", f"{report.generated_at:%d %B %Y}")]
    return ReportDocument(
        title=words.title,
        subtitle=report.objective,
        facts=facts,
        blocks=blocks,
        footer=f"{report.report_id} · content {report.content_hash[:16]} · "
        f"receipt {report.receipt_hash[:16] or '-'}",
    )
