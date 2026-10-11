"""The investigation report as Markdown, DOCX and PDF - all drawn from one object (Phase 51).

Every renderer draws `InvestigationReport.sections()`, so the three exports cannot say different
things. Each carries the report's content hash, so a copy can be checked against the system's.

**The PDF writer is ours** (decision D17 left the library open): a few dozen lines that lay text out
in Helvetica on A4 pages. The report is text - headings and lines - and a text PDF needs no layout
engine; a dependency for it would be a large surface for a small job. Characters outside the PDF's
standard Latin-1 encoding are replaced with readable ASCII ("->" for an arrow, "INR" for the rupee
sign) rather than dropped. The tests read every export back (pypdf, python-docx).
"""

from __future__ import annotations

import io
import textwrap

from docx import Document

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


def to_docx(report: InvestigationReport) -> bytes:
    document = Document()
    document.add_heading("Investigation Report", level=0)
    for line in _header(report):
        document.add_paragraph(line)
    for section in report.sections():
        document.add_heading(section.heading, level=1)
        for line in section.lines:
            document.add_paragraph(line, style="List Bullet")
    buffer = io.BytesIO()
    document.save(buffer)
    return buffer.getvalue()


# --- the PDF -------------------------------------------------------------------------------------

_PAGE_W, _PAGE_H, _MARGIN = 595, 842, 50
_BODY, _HEADING, _LEADING = 9.5, 13, 13
# Helvetica at 9.5 pt averages about 4.9 pt a character; 98 characters fill the 495 pt column.
_WRAP = 98


def _pdf_text(value: str) -> str:
    latin = value.translate(_ASCII).encode("latin-1", "replace").decode("latin-1")
    return latin.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")


def _layout(report: InvestigationReport) -> list[list[tuple[str, float, str]]]:
    """Pages of (font, size, text) lines."""
    rows: list[tuple[str, float, str]] = [("F2", 18, "Investigation Report")]
    rows += [("F1", _BODY, part) for line in _header(report) for part in textwrap.wrap(line, _WRAP)]
    for section in report.sections():
        rows.append(("F1", _BODY, ""))
        rows.append(("F2", _HEADING, section.heading))
        for line in section.lines:
            wrapped = textwrap.wrap(line, _WRAP - 2) or [""]
            rows.append(("F1", _BODY, f"- {wrapped[0]}"))
            rows += [("F1", _BODY, f"  {part}") for part in wrapped[1:]]
    per_page = int((_PAGE_H - 2 * _MARGIN) // _LEADING)
    return [rows[i : i + per_page] for i in range(0, len(rows), per_page)] or [[]]


def to_pdf(report: InvestigationReport) -> bytes:
    pages = _layout(report)
    objects: list[bytes] = []

    def add(body: str | bytes) -> int:
        objects.append(body.encode("latin-1") if isinstance(body, str) else body)
        return len(objects)

    catalog = add("")  # placeholder, filled once the page tree exists
    tree = add("")
    regular = add(
        "<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica /Encoding /WinAnsiEncoding >>"
    )
    bold = add(
        "<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica-Bold /Encoding /WinAnsiEncoding >>"
    )
    kids: list[int] = []
    for number, page in enumerate(pages, start=1):
        commands = ["BT"]
        y = _PAGE_H - _MARGIN
        for face, size, text in page:
            commands.append(
                f"/{face} {size} Tf 1 0 0 1 {_MARGIN} {y:.1f} Tm ({_pdf_text(text)}) Tj"
            )
            y -= _LEADING
        commands.append(
            f"/F1 8 Tf 1 0 0 1 {_MARGIN} 30 Tm ({_pdf_text(report.report_id)} - page {number} of "
            f"{len(pages)} - {_pdf_text(report.content_hash[:23])}) Tj"
        )
        commands.append("ET")
        stream = "\n".join(commands).encode("latin-1")
        content = add(b"<< /Length %d >>\nstream\n" % len(stream) + stream + b"\nendstream")
        kids.append(
            add(
                f"<< /Type /Page /Parent {tree} 0 R /MediaBox [0 0 {_PAGE_W} {_PAGE_H}] "
                f"/Resources << /Font << /F1 {regular} 0 R /F2 {bold} 0 R >> >> "
                f"/Contents {content} 0 R >>"
            )
        )
    objects[catalog - 1] = f"<< /Type /Catalog /Pages {tree} 0 R >>".encode("latin-1")
    objects[tree - 1] = (
        f"<< /Type /Pages /Kids [{' '.join(f'{k} 0 R' for k in kids)}] /Count {len(kids)} >>"
    ).encode("latin-1")
    info = add(
        f"<< /Title ({_pdf_text('Investigation Report ' + report.report_id)}) "
        f"/Subject ({_pdf_text(report.content_hash)}) /Producer (JARVIS) >>"
    )

    out = io.BytesIO()
    out.write(b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\n")
    offsets = []
    for index, body in enumerate(objects, start=1):
        offsets.append(out.tell())
        out.write(b"%d 0 obj\n" % index + body + b"\nendobj\n")
    xref = out.tell()
    out.write(b"xref\n0 %d\n0000000000 65535 f \n" % (len(objects) + 1))
    for offset in offsets:
        out.write(b"%010d 00000 n \n" % offset)
    out.write(
        b"trailer\n<< /Size %d /Root %d 0 R /Info %d 0 R >>\nstartxref\n%d\n%%%%EOF\n"
        % (len(objects) + 1, catalog, info, xref)
    )
    return out.getvalue()
