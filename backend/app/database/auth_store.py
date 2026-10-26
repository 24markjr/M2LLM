"""The Postgres account store (v4 Phase 1a). `scope` defaults to `session_scope`."""

from __future__ import annotations

from collections.abc import Callable
from contextlib import AbstractAsyncContextManager
from datetime import datetime

from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.models import Role, Session, StoredUser
from app.database.session import session_scope
from app.models.tables import SessionRow, UserRow

Scope = Callable[[], AbstractAsyncContextManager[AsyncSession]]


def _user(row: UserRow) -> StoredUser:
    return StoredUser(
        user_id=row.user_id,
        email=row.email,
        name=row.name,
        role=Role(row.role),
        org_id=row.org_id,
        active=row.active,
        created_at=row.created_at,
        last_login_at=row.last_login_at,
        password_hash=row.password_hash,
    )


class PgAuthStore:
    name = "postgres"

    def __init__(self, scope: Scope = session_scope) -> None:
        self._scope = scope

    async def count_users(self) -> int:
        async with self._scope() as session:
            return int((await session.execute(select(func.count(UserRow.user_id)))).scalar_one())

    async def add_user(self, user: StoredUser) -> StoredUser:
        async with self._scope() as session:
            session.add(
                UserRow(
                    user_id=user.user_id,
                    email=user.email,
                    name=user.name,
                    role=user.role.value,
                    org_id=user.org_id,
                    active=user.active,
                    password_hash=user.password_hash,
                    created_at=user.created_at,
                    last_login_at=user.last_login_at,
                )
            )
            await session.flush()
        return user

    async def user_by_email(self, email: str) -> StoredUser | None:
        async with self._scope() as session:
            row = (
                await session.execute(select(UserRow).where(UserRow.email == email.lower()))
            ).scalar_one_or_none()
            return _user(row) if row else None

    async def user_by_id(self, user_id: str) -> StoredUser | None:
        async with self._scope() as session:
            row = await session.get(UserRow, user_id)
            return _user(row) if row else None

    async def users(self, org_id: str | None = None) -> list[StoredUser]:
        async with self._scope() as session:
            query = select(UserRow).order_by(UserRow.email)
            if org_id is not None:
                query = query.where(UserRow.org_id == org_id)
            return [_user(r) for r in (await session.execute(query)).scalars()]

    async def update_user(self, user: StoredUser) -> StoredUser:
        async with self._scope() as session:
            row = await session.get(UserRow, user.user_id)
            if row is not None:
                row.name = user.name
                row.role = user.role.value
                row.org_id = user.org_id
                row.active = user.active
                row.password_hash = user.password_hash
                row.last_login_at = user.last_login_at
                await session.flush()
        return user

    async def add_session(self, session_: Session) -> None:
        async with self._scope() as session:
            session.add(
                SessionRow(
                    token_hash=session_.token_hash,
                    user_id=session_.user_id,
                    created_at=session_.created_at,
                    expires_at=session_.expires_at,
                )
            )
            await session.flush()

    async def session(self, token_hash: str) -> Session | None:
        async with self._scope() as session:
            row = await session.get(SessionRow, token_hash)
            if row is None:
                return None
            return Session(
                token_hash=row.token_hash,
                user_id=row.user_id,
                created_at=row.created_at,
                expires_at=row.expires_at,
            )

    async def drop_session(self, token_hash: str) -> None:
        async with self._scope() as session:
            await session.execute(delete(SessionRow).where(SessionRow.token_hash == token_hash))

    async def drop_sessions_of(self, user_id: str) -> None:
        async with self._scope() as session:
            await session.execute(delete(SessionRow).where(SessionRow.user_id == user_id))

    async def drop_expired(self, now: datetime) -> None:
        async with self._scope() as session:
            await session.execute(delete(SessionRow).where(SessionRow.expires_at <= now))
