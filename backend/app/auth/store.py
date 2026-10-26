"""Where accounts and sessions are kept (Phase 1a): Postgres, or memory without a database."""

from __future__ import annotations

from datetime import datetime
from typing import Protocol

from app.auth.models import Session, StoredUser


class AuthStore(Protocol):
    name: str

    async def count_users(self) -> int: ...

    async def add_user(self, user: StoredUser) -> StoredUser: ...

    async def user_by_email(self, email: str) -> StoredUser | None: ...

    async def user_by_id(self, user_id: str) -> StoredUser | None: ...

    async def users(self, org_id: str | None = None) -> list[StoredUser]: ...

    async def update_user(self, user: StoredUser) -> StoredUser: ...

    async def add_session(self, session: Session) -> None: ...

    async def session(self, token_hash: str) -> Session | None: ...

    async def drop_session(self, token_hash: str) -> None: ...

    async def drop_sessions_of(self, user_id: str) -> None: ...

    async def drop_expired(self, now: datetime) -> None: ...


class MemoryAuthStore:
    name = "memory"

    def __init__(self) -> None:
        self._users: dict[str, StoredUser] = {}
        self._sessions: dict[str, Session] = {}

    async def count_users(self) -> int:
        return len(self._users)

    async def add_user(self, user: StoredUser) -> StoredUser:
        self._users[user.user_id] = user
        return user

    async def user_by_email(self, email: str) -> StoredUser | None:
        return next((u for u in self._users.values() if u.email == email.lower()), None)

    async def user_by_id(self, user_id: str) -> StoredUser | None:
        return self._users.get(user_id)

    async def users(self, org_id: str | None = None) -> list[StoredUser]:
        rows = [u for u in self._users.values() if org_id is None or u.org_id == org_id]
        return sorted(rows, key=lambda u: u.email)

    async def update_user(self, user: StoredUser) -> StoredUser:
        self._users[user.user_id] = user
        return user

    async def add_session(self, session: Session) -> None:
        self._sessions[session.token_hash] = session

    async def session(self, token_hash: str) -> Session | None:
        return self._sessions.get(token_hash)

    async def drop_session(self, token_hash: str) -> None:
        self._sessions.pop(token_hash, None)

    async def drop_sessions_of(self, user_id: str) -> None:
        for key in [k for k, s in self._sessions.items() if s.user_id == user_id]:
            del self._sessions[key]

    async def drop_expired(self, now: datetime) -> None:
        for key in [k for k, s in self._sessions.items() if s.expires_at <= now]:
            del self._sessions[key]
