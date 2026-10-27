"""The investigation report as Markdown (Phase 51), and the characters a PDF font may lack.

HTML, PDF and DOCX are drawn from the designed document since v4 Phase 5 (`document.py`,
`render.py`); the hand-written PDF writer and list-of-lines DOCX they replaced are gone. Markdown
stays a plain text copy of every section. `_ASCII` spells out characters a PDF's built-in font lacks
("->" for an arrow, "INR" for the rupee sign) when no Unicode font is installed.
"""

from __future__ import annotations

from app.schemas.investigation_report import InvestigationReport

# Code points rather than literal characters: several of them look like ASCII and would be
# misread in the source.
_ASCII = str.maketrans(
    {
        0x2192: "->",  # rightwards arrow
        0x2190: "<-",  # leftwards arrow
        0x20B9: "INR ",  # rupee sign
        0x20AC: "EUR ",  # euro sign
        0x00B7: "-",  # middle dot
        0x2014: "-",  # em dash
        0x2013: "-",  # en dash
        0x2018: "'",  # left single quotation mark
        0x2019: "'",  # right single quotation mark
        0x201C: '"',  # left double quotation mark
        0x201D: '"',  # right double quotation mark
        0x2026: "...",  # ellipsis
        0x2212: "-",  # minus sign
        0x00A0: " ",  # no-break space
    }
)


def _header(report: InvestigationReport) -> list[str]:
    return [
        f"Report {report.report_id} - run {report.run_id}"
        + (f" - case {report.case_id}" if report.case_id else ""),
        f"Generated {report.generated_at:%Y-%m-%d %H:%M UTC}"
        + (f" with {report.model}" if report.model else ""),
        f"Content hash {report.content_hash}",
        f"Objective: {report.objective}",
    ]


def to_markdown(report: InvestigationReport) -> str:
    lines = ["# Investigation Report", ""]
    lines += [f"{line}  " for line in _header(report)]
    for section in report.sections():
        lines += ["", f"## {section.heading}", ""]
        lines += [f"- {line}" for line in section.lines]
    return "\n".join(lines) + "\n"
