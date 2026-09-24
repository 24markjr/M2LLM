"""Document upload.

Uploads land in `.agent/uploads/` and are then referenced by name when a mission is created,
exactly like a fixture. That keeps one path through the loader: an uploaded PDF is parsed by
the same code, with the same page map, as one that shipped with the repo - so a citation into
an upload is as checkable as a citation into a fixture.

The size ceiling is enforced while streaming, not after. Reading a file into memory to find
out it is too large is how a single request takes down the process.
"""

from __future__ import annotations

import asyncio
from pathlib import Path

from fastapi import APIRouter, UploadFile, status

from app.api.errors import ApiError
from app.core.config import get_settings
from app.core.logging import get_logger
from app.schemas.common import JarvisModel
from app.tools.loader import DocumentLoadError, load_document

log = get_logger(__name__)
router = APIRouter(prefix="/documents", tags=["documents"])

MAX_UPLOAD_BYTES = 25 * 1024 * 1024
CHUNK = 64 * 1024

# Extensions the loader can actually parse. Accepting anything else would let a mission be
# created against a file that silently contributes nothing.
ALLOWED = {".txt", ".md", ".csv", ".pdf", ".json"}


class UploadedDocument(JarvisModel):
    document_id: str
    name: str
    kind: str
    bytes: int
    summary: str = ""
    truncated: bool = False


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
        if suffix not in ALLOWED:
            raise ApiError(
                "UNSUPPORTED_DOCUMENT_TYPE",
                f"{name} cannot be parsed; supported types are {', '.join(sorted(ALLOWED))}",
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                details={"name": name, "suffix": suffix},
            )

        path = target / name
        written = await _write(upload, path, name)

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
            )
        )

    return results


async def _write(upload: UploadFile, path: Path, name: str) -> int:
    """Buffer the upload, enforcing the ceiling before anything reaches the disk.

    The size check runs while reading, so an oversized file is refused after 25 MB rather
    than after all of it. Nothing is written until it has passed, which means a rejected
    upload never leaves a partial file behind to be cleaned up. The write itself goes to a
    thread: a synchronous 25 MB write on the event loop would stall every other request,
    including the SSE streams of runs already in flight.
    """
    chunks: list[bytes] = []
    written = 0
    while chunk := await upload.read(CHUNK):
        written += len(chunk)
        if written > MAX_UPLOAD_BYTES:
            raise ApiError(
                "DOCUMENT_TOO_LARGE",
                f"{name} exceeds the {MAX_UPLOAD_BYTES // (1024 * 1024)} MB limit",
                status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                details={"name": name, "limit_bytes": MAX_UPLOAD_BYTES},
            )
        chunks.append(chunk)

    await asyncio.to_thread(path.write_bytes, b"".join(chunks))
    return written
