"""Document loading for real inputs.

Until now documents were small text fixtures held in memory. Real inputs are PDFs of a
hundred pages and CSVs of a thousand rows, and they break three things at once: nothing
read PDFs, tools returned every match they found, and those matches went whole into a
prompt with a four-thousand-token budget.

The rule this module follows, and the reason it is not simply `text[:10000]`:

**Truncation is always visible.** When a document is too large to load whole, the loaded
portion is marked and the omission is reported. A silent truncation would let the agent
conclude "no contradiction found" from evidence it never saw — which is precisely the
failure this project exists to prevent. A finding built on partial input must be
distinguishable from one built on all of it.
"""

from __future__ import annotations

from pathlib import Path

from pydantic import Field

from app.core.logging import get_logger
from app.schemas.common import JarvisModel

log = get_logger(__name__)

# A page of dense text is roughly 3 kB. 400 kB is about 130 pages - enough for a real
# report, bounded enough that a single document cannot exhaust memory or a prompt budget.
MAX_DOCUMENT_CHARS = 400_000
MAX_PDF_PAGES = 200
# Rows beyond this are summarised rather than listed. A thousand-row CSV is analysed by
# aggregate, not by reciting it into a prompt.
MAX_CSV_ROWS = 500

TRUNCATION_MARKER = "[TRUNCATED]"


class LoadedDocument(JarvisModel):
    """A document as loaded, honest about what was left out."""

    document_id: str
    text: str
    kind: str = "text"
    truncated: bool = False
    omitted_note: str = ""
    page_count: int = 0
    line_count: int = 0
    size_bytes: int = 0
    # Line number at which each page begins, in order. Empty for non-paginated documents.
    # This is what lets a tool report `report.pdf:p12` instead of `report.pdf:r847`.
    page_starts: list[int] = Field(default_factory=list)

    @property
    def summary(self) -> str:
        detail = f"{self.line_count} line(s)"
        if self.page_count:
            detail = f"{self.page_count} page(s), {detail}"
        if self.truncated:
            detail += f" - {self.omitted_note}"
        return detail


class DocumentLoadError(RuntimeError):
    """The file could not be read at all. Distinct from being too large to read whole."""


def load_pdf(path: Path, *, max_pages: int = MAX_PDF_PAGES) -> LoadedDocument:
    """Extract text from a PDF, one page at a time, keeping page boundaries visible.

    Each page is preceded by a marker so a line locator can still be traced back to a page
    by a human reading the report. Pages beyond the limit are omitted and said to be.
    """
    try:
        from pypdf import PdfReader
    except ImportError as exc:  # pragma: no cover - dependency is declared
        raise DocumentLoadError(f"pypdf is required to read {path.name}") from exc

    try:
        reader = PdfReader(str(path))
        total = len(reader.pages)
        pages = reader.pages[:max_pages]
        chunks: list[str] = []
        page_starts: list[int] = []
        line_number = 1
        for number, page in enumerate(pages, start=1):
            extracted = (page.extract_text() or "").strip()
            body = extracted or "(no extractable text on this page)"
            page_starts.append(line_number)
            marker = f"--- page {number} ---"
            chunks.append(marker)
            chunks.append(body)
            line_number += 1 + body.count("\n") + 1
        text = "\n".join(chunks)
    except DocumentLoadError:
        raise
    except Exception as exc:
        raise DocumentLoadError(f"could not read {path.name}: {type(exc).__name__}: {exc}") from exc

    truncated = total > max_pages
    return LoadedDocument(
        document_id=path.name,
        text=text,
        kind="pdf",
        truncated=truncated,
        omitted_note=f"pages {max_pages + 1}-{total} were not read" if truncated else "",
        page_count=min(total, max_pages),
        line_count=text.count("\n") + 1,
        size_bytes=path.stat().st_size,
        page_starts=page_starts,
    )


def load_text(path: Path, *, max_chars: int = MAX_DOCUMENT_CHARS) -> LoadedDocument:
    raw = path.read_text(encoding="utf-8", errors="replace")
    truncated = len(raw) > max_chars
    text = raw[:max_chars] + (f"\n{TRUNCATION_MARKER}" if truncated else "")

    return LoadedDocument(
        document_id=path.name,
        text=text,
        kind="csv" if path.suffix.lower() == ".csv" else "text",
        truncated=truncated,
        omitted_note=(
            f"{len(raw) - max_chars} of {len(raw)} characters were not read" if truncated else ""
        ),
        line_count=text.count("\n") + 1,
        size_bytes=path.stat().st_size,
    )


def load_document(path: Path) -> LoadedDocument:
    """Load one document by extension."""
    if not path.exists():
        raise DocumentLoadError(f"no such file: {path}")
    if path.suffix.lower() == ".pdf":
        return load_pdf(path)
    return load_text(path)


def load_documents(paths: list[Path]) -> tuple[dict[str, str], list[LoadedDocument]]:
    """Load several documents, returning the text map tools consume and the load report.

    A file that cannot be read is skipped and logged rather than failing the run - one
    unreadable attachment should not abandon an investigation over the others - but it is
    never silently treated as empty.
    """
    documents: dict[str, str] = {}
    loaded: list[LoadedDocument] = []

    for path in paths:
        try:
            document = load_document(path)
        except DocumentLoadError as exc:
            log.warning("document_load_failed", path=str(path), error=str(exc))
            continue
        documents[document.document_id] = document.text
        loaded.append(document)
        if document.truncated:
            log.warning(
                "document_truncated",
                document=document.document_id,
                omitted=document.omitted_note,
            )

    return documents, loaded


class ResultCap(JarvisModel):
    """What a tool returned versus what it found.

    Carried in every capped tool output. `found` is the honest total; `returned` is what fit.
    A reader - human or model - can always tell whether they are looking at everything.
    """

    found: int = Field(default=0, ge=0)
    returned: int = Field(default=0, ge=0)

    @property
    def capped(self) -> bool:
        return self.found > self.returned

    def note(self) -> str:
        if not self.capped:
            return ""
        return f"{self.returned} of {self.found} shown; {self.found - self.returned} not returned"


def cap[T](items: list[T], limit: int) -> tuple[list[T], ResultCap]:
    """Take the first `limit` items and report how many there were."""
    return items[:limit], ResultCap(found=len(items), returned=min(len(items), limit))


def page_for_line(page_starts: list[int], line: int) -> int | None:
    """Which page a line falls on, given where each page begins.

    Returns None for a document with no pages, so a caller can fall back to a line
    locator rather than inventing a page number.
    """
    if not page_starts:
        return None
    page = 0
    for index, start in enumerate(page_starts, start=1):
        if line >= start:
            page = index
        else:
            break
    return page or 1


def source_ref(document_id: str, line: int, page_starts: dict[str, list[int]]) -> str:
    """The citation a tool emits for a location.

    Paginated documents cite a page, because that is what a human can turn to. Everything
    else cites a line. Both resolve; only one is checkable by a reader holding the PDF.
    """
    page = page_for_line(page_starts.get(document_id, []), line)
    if page is not None:
        return f"{document_id}:p{page}"
    return f"{document_id}:r{line}"
