"""Document upload.

Uploads land in `.agent/uploads/` and are then referenced by name when a mission is created,
exactly like a fixture. That keeps one path through the loader: an uploaded PDF is parsed by
the same code, with the same page map, as one that shipped with the repo - so a citation into
an upload is as checkable as a citation into a fixture.

The size ceiling is enforced while streaming, not after. Reading a file into memory to find
out it is too large is how a single request takes down the process.

Phase 38: the accepted types are the format registry's (`app/tools/formats.py`), and the console
reads them from `GET /documents/formats`, so the server and the file picker cannot disagree. Each
upload reports its parser and SHA-256 (Member 2's provenance), and whether it yields text yet.
`GET /documents` lists earlier uploads so a new mission can reuse them.
"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from pathlib import Path

from fastapi import APIRouter, UploadFile, status
from pydantic import Field

from app.api.errors import ApiError
from app.core.config import get_settings
from app.core.logging import get_logger
from app.llm import get_provider
from app.schemas.common import JarvisModel
from app.schemas.trust import InjectionScan
from app.security.injection import scan
from app.tools.formats import (
    FORMATS,
    FormatKind,
    FormatSpec,
    prepare,
    spec_for,
    supported_extensions,
)
from app.tools.loader import DocumentLoadError, load_document

log = get_logger(__name__)
router = APIRouter(prefix="/documents", tags=["documents"])

MAX_UPLOAD_BYTES = 25 * 1024 * 1024
# A video is large and contributes only its transcript, but refusing every real recording at 25 MB
# would make the type pointless. Streamed to disk, so the size costs no memory.
MAX_VIDEO_BYTES = 500 * 1024 * 1024
CHUNK = 64 * 1024

# Extensions the loader can actually parse: the format registry's, nothing else. Accepting anything
# else would let a mission be created against a file that silently contributes nothing.
ALLOWED = supported_extensions()


class UploadedDocument(JarvisModel):
    document_id: str
    name: str
    kind: str
    bytes: int
    summary: str = ""
    truncated: bool = False
    # The prompt-injection scan of what was parsed (Phase 27). A flag is a warning shown before a
    # mission starts, never a rejection: the document is still accepted and read as data.
    injection: InjectionScan = Field(default_factory=InjectionScan)
    # Provenance (Phase 38).
    parser: str = ""
    sha256: str = ""
    # False for an image before OCR or a video without a transcript: accepted, kept, and excluded
    # from a mission's evidence until it has text. `note` says why.
    has_text: bool = True
    note: str = ""
    # What an image, scan, video or audio file was understood to contain (Phase 39): lines read,
    # spoken segments heard, lines seen and by which model. Empty for plain documents.
    understood: str = ""


class StoredDocument(JarvisModel):
    """An earlier upload, offered again to a new mission."""

    name: str
    kind: str
    bytes: int
    uploaded_at: datetime


@router.post("", response_model=list[UploadedDocument], status_code=status.HTTP_201_CREATED)
async def upload_documents(files: list[UploadFile]) -> list[UploadedDocument]:
    """Store uploads and report what each one parsed as.

    The response is the parse result, not an acknowledgement. A client that only learns a
    file was accepted still does not know whether it will contribute anything to a run -
    a 12-page scanned PDF with no text layer uploads perfectly and yields nothing.
    """
    target = get_settings().agent_dir / "uploads"
    target.mkdir(parents=True, exist_ok=True)

    results: list[UploadedDocument] = []
    for upload in files:
        name = Path(upload.filename or "").name
        if not name:
            raise ApiError(
                "MISSING_FILENAME",
                "every uploaded file must have a name",
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            )
        suffix = Path(name).suffix.lower()
        if suffix not in ALLOWED or name.startswith("."):
            raise ApiError(
                "UNSUPPORTED_DOCUMENT_TYPE",
                f"{name} cannot be parsed; supported types are {', '.join(sorted(ALLOWED))}",
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                details={"name": name, "suffix": suffix},
            )

        path = target / name
        spec = spec_for(path)
        limit = MAX_VIDEO_BYTES if spec and spec.kind is FormatKind.VIDEO else MAX_UPLOAD_BYTES
        written = await _write(upload, path, name, limit)

        # Understand an image, scan, video or audio file now (Phase 39), so the response says what
        # was read, seen and heard and a mission using it later waits for nothing.
        await prepare([path], get_provider())
        try:
            document = load_document(path)
        except DocumentLoadError as exc:
            # Remove it. A stored file the loader cannot read would be offered to the next
            # mission as a valid attachment and contribute nothing.
            await asyncio.to_thread(path.unlink, True)
            raise ApiError(
                "DOCUMENT_UNREADABLE",
                f"{name} was uploaded but could not be parsed: {exc}",
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                details={"name": name},
            ) from exc

        results.append(
            UploadedDocument(
                document_id=document.document_id,
                name=name,
                kind=str(document.kind),
                bytes=written,
                summary=document.summary,
                truncated=document.truncated,
                injection=scan(document.text, source=name),
                parser=document.parser,
                sha256=document.sha256,
                has_text=document.has_text,
                note="" if document.has_text else document.text.splitlines()[-1],
                understood=_understood(document.sha256),
            )
        )
        log.info(
            "document_uploaded",
            name=name,
            kind=document.kind,
            parser=document.parser,
            sha256=document.sha256,
            has_text=document.has_text,
        )

    return results


def _understood(sha256: str) -> str:
    from app.tools.media import cached, describe

    found = cached(sha256) if get_settings().media_understanding else None
    return describe(found) if found is not None and found.has_text else ""


@router.get("/formats", response_model=list[FormatSpec])
async def formats() -> list[FormatSpec]:
    """Every file type a mission can read, which parser reads it, and how it becomes text."""
    return FORMATS


@router.get("", response_model=list[StoredDocument])
async def list_uploads() -> list[StoredDocument]:
    """Earlier uploads, newest first, so a new mission can reuse them without uploading again."""
    target = get_settings().agent_dir / "uploads"
    if not target.is_dir():
        return []
    stored = []
    for path in target.iterdir():
        spec = spec_for(path)
        if not path.is_file() or spec is None or path.name.startswith("."):
            continue
        stat = path.stat()
        stored.append(
            StoredDocument(
                name=path.name,
                kind=spec.kind.value,
                bytes=stat.st_size,
                uploaded_at=datetime.fromtimestamp(stat.st_mtime, tz=UTC),
            )
        )
    return sorted(stored, key=lambda d: (d.uploaded_at, d.name), reverse=True)


async def _write(upload: UploadFile, path: Path, name: str, limit: int) -> int:
    """Stream the upload to a temporary file, enforcing the ceiling while reading.

    The size check runs while reading, so an oversized file is refused at the limit rather than
    after all of it. It streams to `<name>.part` and is renamed into place only when complete, so a
    refused or broken upload never leaves a file a mission could pick up. (Until Phase 38 the whole
    upload was buffered in memory first, which was fine at 25 MB and is not for a video.) Disk
    writes go to a thread so they never stall the event loop and the SSE streams on it.
    """
    partial = path.with_name(f".{path.name}.part")
    written = 0
    handle = await asyncio.to_thread(partial.open, "wb")
    try:
        while chunk := await upload.read(CHUNK):
            written += len(chunk)
            if written > limit:
                raise ApiError(
                    "DOCUMENT_TOO_LARGE",
                    f"{name} exceeds the {limit // (1024 * 1024)} MB limit",
                    status_code=status.HTTP_413_CONTENT_TOO_LARGE,
                    details={"name": name, "limit_bytes": limit},
                )
            await asyncio.to_thread(handle.write, chunk)
    except BaseException:
        await asyncio.to_thread(handle.close)
        await asyncio.to_thread(partial.unlink, True)
        raise
    await asyncio.to_thread(handle.close)
    await asyncio.to_thread(partial.replace, path)
    return written
