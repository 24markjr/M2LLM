"""Content-addressed, write-once storage for evidence bytes (Phase 43).

`.agent/evidence/<first two hex digits>/<sha256>`: the file's name is its hash, so a file is found
by what it is, not by what someone called it, and two identical uploads are stored once. A stored
file is never written again: `put` of bytes already present checks them and leaves them alone.

This is the only module that writes under `.agent/evidence/` (an invariant test checks the source).
The named copy missions parse stays in `.agent/uploads/`; this one is the original kept for proof.
"""

from __future__ import annotations

import hashlib
import shutil
from pathlib import Path

from app.core.config import get_settings


def evidence_root() -> Path:
    return get_settings().agent_dir / "evidence"


def path_for(sha256: str) -> Path:
    return evidence_root() / sha256[:2] / sha256


def hash_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1 << 16), b""):
            digest.update(block)
    return digest.hexdigest()


def put(source: Path) -> tuple[str, Path]:
    """Store a copy of `source` under its hash. Returns the hash and where it is kept.

    Write-once: when the hash is already stored, nothing is written. The copy goes to a temporary
    name first and is renamed into place, so a crash never leaves a partial file under a real hash.
    """
    sha = hash_file(source)
    target = path_for(sha)
    if target.exists():
        return sha, target
    target.parent.mkdir(parents=True, exist_ok=True)
    partial = target.with_suffix(".part")
    shutil.copyfile(source, partial)
    if hash_file(partial) != sha:  # the source changed while it was being copied
        partial.unlink(missing_ok=True)
        raise OSError(f"{source.name} changed while it was being stored")
    partial.replace(target)
    target.chmod(0o444)  # read-only: a reminder on disk, not the protection itself
    return sha, target


def rehash(sha256: str) -> str | None:
    """The hash of what is stored under `sha256` now, or None when it is missing."""
    target = path_for(sha256)
    return hash_file(target) if target.is_file() else None
