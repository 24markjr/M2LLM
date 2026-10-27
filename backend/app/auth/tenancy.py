"""Customer organisations with isolated data (v4 Phase 1c).

The organisation of the signed-in user is set once per request by the auth middleware, in a context
variable, and every store reads it from there: runs, cases, evidence, uploads and workspaces are
stamped with it when created and filtered by it when read. A task started inside a request (a
mission, background indexing) inherits it, because asyncio copies the context into new tasks.

Outside a request - the CLI, tests, accounts switched off - the organisation is `default`, which is
also where everything created before Phase 1c lives, so an existing installation keeps its data.

Another organisation's resource is reported as not found, never as forbidden: a 403 would confirm
that the run or case exists.
"""

from __future__ import annotations

import re
from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from pathlib import Path

from app.auth.models import DEFAULT_ORG
from app.core.config import get_settings

__all__ = ["DEFAULT_ORG", "ORG_PATTERN"]

ORG_PATTERN = re.compile(r"^[a-z0-9][a-z0-9-]{1,47}$")

_org: ContextVar[str] = ContextVar("jarvis_org", default=DEFAULT_ORG)


def current_org() -> str:
    return _org.get()


def set_org(org_id: str) -> None:
    """For the auth middleware: the rest of this request belongs to `org_id`."""
    _org.set(org_id)


@contextmanager
def use_org(org_id: str) -> Iterator[None]:
    token = _org.set(org_id)
    try:
        yield
    finally:
        _org.reset(token)


def uploads_dir(org_id: str | None = None) -> Path:
    """Where an organisation's uploads live. The default organisation keeps `.agent/uploads/`
    itself, so earlier uploads stay where they were; any other gets a folder under `.orgs/`, inside
    the same volume, so a redeploy keeps it too."""
    org = org_id or current_org()
    root = get_settings().agent_dir / "uploads"
    return root if org == DEFAULT_ORG else root / ".orgs" / org


def scoped_workspace(workspace_id: str) -> str:
    """The stored id of a workspace: two organisations may both call theirs `main`."""
    org = current_org()
    return workspace_id if org == DEFAULT_ORG else f"{org}~{workspace_id}"


def visible_workspace(stored_id: str) -> str | None:
    """A stored workspace id as the current organisation names it, or None if it is not theirs."""
    org = current_org()
    if org == DEFAULT_ORG:
        return None if "~" in stored_id else stored_id
    prefix = f"{org}~"
    return stored_id[len(prefix) :] if stored_id.startswith(prefix) else None


def is_bare_name(name: str) -> bool:
    """A file name with no directory in it. Anything else could reach outside the uploads."""
    return (
        bool(name)
        and name not in {".", ".."}
        and "/" not in name
        and "\\" not in name
        and "\x00" not in name
        and ":" not in name
        and not name.startswith(".")
    )
