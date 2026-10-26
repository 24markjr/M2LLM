"""The account model (Phase 1a): users, their role and organisation, and sessions."""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum

from pydantic import Field

from app.schemas.common import JarvisModel, utcnow


class Role(StrEnum):
    """What a person may do. Ordered from least to most; see `permissions.py` for the matrix."""

    VIEWER = "viewer"  # reads everything in their organisation, changes nothing
    REVIEWER = "reviewer"  # a viewer who also reviews and challenges findings
    ANALYST = "analyst"  # runs investigations, files evidence, manages cases
    ADMIN = "admin"  # everything, including accounts and deleting everything


DEFAULT_ORG = "default"


class User(JarvisModel):
    """An account as the API shows it. The password hash never leaves the store."""

    user_id: str
    email: str
    name: str = ""
    role: Role = Role.ANALYST
    org_id: str = DEFAULT_ORG
    active: bool = True
    created_at: datetime = Field(default_factory=utcnow)
    last_login_at: datetime | None = None


class StoredUser(User):
    password_hash: str = ""


class Session(JarvisModel):
    """A signed-in browser. Only the SHA-256 of the token is stored; the token is the cookie."""

    token_hash: str
    user_id: str
    created_at: datetime = Field(default_factory=utcnow)
    expires_at: datetime
