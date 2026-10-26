"""Accounts over HTTP (v4 Phase 1a): sign in and out, who am I, my password, and - for an admin -
the accounts of their organisation. Signing in sets an HttpOnly cookie; nothing else carries the
session, so the browser's EventSource stream is authenticated like every other request."""

from __future__ import annotations

from fastapi import APIRouter, Request, Response, status
from pydantic import Field

from app.api.errors import ApiError
from app.auth.models import Role, User
from app.auth.passwords import hash_password, verify_password, weak_reason
from app.auth.service import (
    COOKIE,
    clear_failures,
    create_user,
    ensure_first_admin,
    get_auth_store,
    public,
    record_failure,
    sign_in,
    throttled,
    token_hash,
)
from app.core.config import get_settings
from app.review.service import audit
from app.schemas.common import JarvisModel

router = APIRouter(prefix="/auth", tags=["auth"])


class LoginRequest(JarvisModel):
    email: str = Field(min_length=3, max_length=254)
    password: str = Field(min_length=1, max_length=256)


class PasswordChange(JarvisModel):
    current: str = Field(min_length=1, max_length=256)
    new: str = Field(min_length=1, max_length=256)


class NewUser(JarvisModel):
    email: str = Field(min_length=3, max_length=254, pattern=r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
    name: str = Field(default="", max_length=128)
    role: Role = Role.ANALYST
    password: str = Field(min_length=1, max_length=256)


class UserUpdate(JarvisModel):
    name: str | None = Field(default=None, max_length=128)
    role: Role | None = None
    active: bool | None = None
    password: str | None = Field(default=None, max_length=256)


# When accounts are switched off (tests, the static demo), every request acts as this user.
LOCAL = User(user_id="U-local", email="local@jarvis", name="Local", role=Role.ADMIN)


def current(request: Request) -> User:
    user = getattr(request.state, "user", None)
    if isinstance(user, User):
        return user
    if not get_settings().auth_required:
        return LOCAL
    raise ApiError("UNAUTHENTICATED", "sign in first", status_code=status.HTTP_401_UNAUTHORIZED)


def _strong(password: str) -> None:
    reason = weak_reason(password)
    if reason:
        raise ApiError(
            "WEAK_PASSWORD",
            f"the password needs {reason}",
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
        )


@router.post("/login", response_model=User)
async def login(body: LoginRequest, request: Request, response: Response) -> User:
    """Sign in. Five failures for one email in 15 minutes lock it for the rest of the window."""
    key = body.email.strip().lower()
    if throttled(key):
        raise ApiError(
            "LOGIN_RATE_LIMITED",
            "too many failed attempts; try again in 15 minutes",
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
        )
    store = await get_auth_store()
    await ensure_first_admin(store)
    signed = await sign_in(store, key, body.password)
    if signed is None:
        record_failure(key)
        await audit("auth.login_failed", actor=key[:128], target="auth")
        raise ApiError(
            "INVALID_CREDENTIALS",
            "the email or the password is wrong",
            status_code=status.HTTP_401_UNAUTHORIZED,
        )
    user, token = signed
    clear_failures(key)
    settings = get_settings()
    response.set_cookie(
        COOKIE,
        token,
        max_age=settings.session_hours * 3600,
        httponly=True,
        secure=settings.cookie_secure,
        samesite="lax",
        path="/",
    )
    await audit("auth.login", actor=user.email, target="auth")
    return public(user)


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
async def logout(request: Request, response: Response) -> None:
    token = request.cookies.get(COOKIE, "")
    if token:
        await (await get_auth_store()).drop_session(token_hash(token))
    response.delete_cookie(COOKIE, path="/")


@router.get("/me", response_model=User)
async def me(request: Request) -> User:
    return current(request)


@router.post("/password", status_code=status.HTTP_204_NO_CONTENT)
async def change_password(body: PasswordChange, request: Request) -> None:
    """Change my password. Every other session of mine is signed out."""
    user = current(request)
    store = await get_auth_store()
    stored = await store.user_by_id(user.user_id)
    if stored is None or not verify_password(body.current, stored.password_hash):
        raise ApiError(
            "INVALID_CREDENTIALS",
            "the current password is wrong",
            status_code=status.HTTP_403_FORBIDDEN,
        )
    _strong(body.new)
    await store.update_user(stored.model_copy(update={"password_hash": hash_password(body.new)}))
    await store.drop_sessions_of(stored.user_id)


@router.get("/users", response_model=list[User])
async def list_users(request: Request) -> list[User]:
    """The accounts of the admin's organisation."""
    admin = current(request)
    return [public(u) for u in await (await get_auth_store()).users(admin.org_id)]


@router.post("/users", response_model=User, status_code=status.HTTP_201_CREATED)
async def add_user(body: NewUser, request: Request) -> User:
    admin = current(request)
    store = await get_auth_store()
    if await store.user_by_email(body.email) is not None:
        raise ApiError(
            "EMAIL_TAKEN",
            f"{body.email} already has an account",
            status_code=status.HTTP_409_CONFLICT,
        )
    _strong(body.password)
    user = await create_user(
        store,
        email=body.email,
        password=body.password,
        role=body.role,
        name=body.name,
        org_id=admin.org_id,
    )
    return public(user)


@router.patch("/users/{user_id}", response_model=User)
async def update_user(user_id: str, body: UserUpdate, request: Request) -> User:
    """Rename, change role, (de)activate or reset the password of an account in my organisation.
    An admin cannot demote or deactivate themselves: an organisation must keep an admin."""
    admin = current(request)
    store = await get_auth_store()
    user = await store.user_by_id(user_id)
    if user is None or user.org_id != admin.org_id:
        raise ApiError(
            "USER_NOT_FOUND", f"no account {user_id}", status_code=status.HTTP_404_NOT_FOUND
        )
    if user.user_id == admin.user_id and (
        body.active is False or (body.role is not None and body.role is not Role.ADMIN)
    ):
        raise ApiError(
            "SELF_LOCKOUT",
            "you cannot demote or deactivate your own account",
            status_code=status.HTTP_409_CONFLICT,
        )
    changes: dict[str, object] = {}
    if body.name is not None:
        changes["name"] = body.name
    if body.role is not None:
        changes["role"] = body.role
    if body.active is not None:
        changes["active"] = body.active
    if body.password is not None:
        _strong(body.password)
        changes["password_hash"] = hash_password(body.password)
    updated = await store.update_user(user.model_copy(update=changes))
    if body.active is False or body.password is not None or body.role is not None:
        await store.drop_sessions_of(user.user_id)
    return public(updated)
