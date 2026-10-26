"""Signing in and out, sessions, the first admin, and login throttling (v4 Phase 1a)."""

from __future__ import annotations

import hashlib
import secrets
import time
from datetime import timedelta

from app.auth.models import DEFAULT_ORG, Role, Session, StoredUser, User
from app.auth.passwords import hash_password, verify_password
from app.auth.store import AuthStore, MemoryAuthStore
from app.core.config import get_settings
from app.core.logging import get_logger
from app.schemas.common import utcnow

log = get_logger(__name__)

COOKIE = "jarvis_session"

_memory_store = MemoryAuthStore()
_database: bool | None = None
_checked_at: float | None = None


async def get_auth_store() -> AuthStore:
    global _database, _checked_at
    from app.database.session import recheck

    _database, _checked_at = await recheck(_database, _checked_at)
    if _database:
        from app.database.auth_store import PgAuthStore

        return PgAuthStore()
    return _memory_store


def reset_memory_store() -> None:
    """Tests: a fresh in-memory store."""
    global _memory_store
    _memory_store = MemoryAuthStore()


def token_hash(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def new_user_id() -> str:
    return f"U-{secrets.token_hex(6)}"


def public(user: StoredUser) -> User:
    return User.model_validate(user.model_dump(exclude={"password_hash"}))


async def create_user(
    store: AuthStore,
    *,
    email: str,
    password: str,
    role: Role,
    name: str = "",
    org_id: str = DEFAULT_ORG,
) -> StoredUser:
    user = StoredUser(
        user_id=new_user_id(),
        email=email.strip().lower(),
        name=name.strip(),
        role=role,
        org_id=org_id,
        password_hash=hash_password(password),
    )
    return await store.add_user(user)


async def ensure_first_admin(store: AuthStore) -> None:
    """With no account at all, create the admin named in ADMIN_EMAIL / ADMIN_PASSWORD. Never
    touches an existing account, so changing the setting later cannot reset a password."""
    settings = get_settings()
    if not settings.admin_email or not settings.admin_password:
        return
    if await store.count_users() > 0:
        return
    await create_user(
        store,
        email=settings.admin_email,
        password=settings.admin_password,
        role=Role.ADMIN,
        name="Administrator",
    )
    log.info("first_admin_created", email=settings.admin_email.lower())


# --- login throttling ---------------------------------------------------------------------------

_failures: dict[str, list[float]] = {}
MAX_FAILURES = 5
WINDOW_S = 15 * 60


def throttled(key: str) -> bool:
    now = time.monotonic()
    recent = [t for t in _failures.get(key, []) if now - t < WINDOW_S]
    _failures[key] = recent
    return len(recent) >= MAX_FAILURES


def record_failure(key: str) -> None:
    _failures.setdefault(key, []).append(time.monotonic())


def clear_failures(key: str) -> None:
    _failures.pop(key, None)


# --- sessions -----------------------------------------------------------------------------------


async def sign_in(store: AuthStore, email: str, password: str) -> tuple[StoredUser, str] | None:
    """The user and a new session token, or None. Wrong email and wrong password look the same."""
    user = await store.user_by_email(email.strip().lower())
    if user is None or not user.active or not verify_password(password, user.password_hash):
        return None
    token = secrets.token_urlsafe(32)
    now = utcnow()
    await store.add_session(
        Session(
            token_hash=token_hash(token),
            user_id=user.user_id,
            created_at=now,
            expires_at=now + timedelta(hours=get_settings().session_hours),
        )
    )
    signed_in = user.model_copy(update={"last_login_at": now})
    await store.update_user(signed_in)
    await store.drop_expired(now)
    return signed_in, token


async def user_for(store: AuthStore, token: str) -> StoredUser | None:
    """The active user a session token belongs to, or None when unknown, expired or deactivated."""
    session = await store.session(token_hash(token))
    if session is None:
        return None
    if session.expires_at <= utcnow():
        await store.drop_session(session.token_hash)
        return None
    user = await store.user_by_id(session.user_id)
    return user if user is not None and user.active else None
