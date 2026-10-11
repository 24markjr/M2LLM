# ADR-017 — The report's PDF is written by a small in-house text writer (decision D17)

## Status

Accepted — 2026-10-11 (Phase 51)

## Context

D17 decided one structured report rendered to PDF, DOCX and JSON, and left the PDF library to Phase
51. The report is headings and lines of text. `python-docx` (DOCX) and `pypdf` (reading PDFs) were
already dependencies; no PDF writer was.

## Decision

A ~90-line writer (`reporting/export.py` `to_pdf`): Helvetica and Helvetica-Bold, A4, wrapped lines,
a footer with page numbers and the content hash, an Info dictionary carrying the hash. Characters
outside Latin-1 are mapped to readable ASCII ("->", "INR", quotes) rather than dropped. The tests read
every export back with `pypdf` and `python-docx`.

## Alternatives considered

- **reportlab / fpdf2**: real layout engines, and new dependencies (one of them large) for text a
  page writer handles; worth it if the report gains tables, charts or embedded images.
- **HTML to PDF (WeasyPrint)**: native libraries on Windows, a heavy install for a demo machine.

## Consequences

- No tables or images in the PDF; the DOCX and JSON carry the same content.
- Non-Latin text (Hindi, say) is transliterated to `?` beyond the mapped characters - acceptable for
  the current corpora, and the trigger to adopt a library with embedded Unicode fonts.
