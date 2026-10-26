"""v4 Phase 1a: accounts, sessions and roles in front of every route."""

from __future__ import annotations

import re
from collections.abc import Iterator

import pytest
from httpx import ASGITransport, AsyncClient

from app.api.app import create_app
from app.auth import service
from app.auth.models import Role
from app.auth.passwords import hash_password, verify_password, weak_reason
from app.auth.permissions import allowed
from app.core.config import get_settings

ADMIN = ("admin@tessera.test", "Adm1nPassword!")


@pytest.fixture(autouse=True)
def _accounts_on(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    settings = get_settings()
    monkeypatch.setattr(settings, "auth_required", True)
    monkeypatch.setattr(settings, "admin_email", ADMIN[0])
    monkeypatch.setattr(settings, "admin_password", ADMIN[1])
    service.reset_memory_store()
    service._failures.clear()
    yield


def _client() -> AsyncClient:
    return AsyncClient(transport=ASGITransport(app=create_app()), base_url="http://test")


async def _login(client: AsyncClient, email: str, password: str) -> int:
    body = {"email": email, "password": password}
    return (await client.post("/api/v1/auth/login", json=body)).status_code


# --- passwords and the role matrix -----------------------------------------------------------


def test_passwords_are_salted_hashes_and_weak_ones_are_named() -> None:
    a, b = hash_password("Correct-horse-1"), hash_password("Correct-horse-1")
    assert a != b and a.startswith("scrypt$")
    assert verify_password("Correct-horse-1", a) and not verify_password("wrong", a)
    assert not verify_password("x", "garbage")
    assert weak_reason("short1A") and weak_reason("alllowercase123")
    assert not weak_reason("Good-pass-123")


@pytest.mark.parametrize(
    ("role", "method", "path", "ok"),
    [
        (Role.VIEWER, "GET", "/api/v1/missions", True),
        (Role.VIEWER, "POST", "/api/v1/missions", False),
        (Role.VIEWER, "POST", "/api/v1/context/retrieve", True),
        (Role.REVIEWER, "POST", "/api/v1/missions/r/findings/F-001/review", True),
        (Role.REVIEWER, "POST", "/api/v1/missions/r/findings/F-001/challenge", True),
        (Role.REVIEWER, "DELETE", "/api/v1/cases/C-1", False),
        (Role.ANALYST, "POST", "/api/v1/missions", True),
        (Role.ANALYST, "DELETE", "/api/v1/missions", False),
        (Role.ANALYST, "GET", "/api/v1/auth/users", False),
        (Role.ADMIN, "DELETE", "/api/v1/missions", True),
        (Role.VIEWER, "POST", "/api/v1/auth/password", True),
    ],
)
def test_the_role_matrix(role: Role, method: str, path: str, ok: bool) -> None:
    assert allowed(role, method, path) is ok


# --- every route is behind the sign-in -------------------------------------------------------


async def test_every_api_route_refuses_an_anonymous_caller() -> None:
    app = create_app()
    # From the OpenAPI schema: it lists every route, however routers are nested.
    routes = [
        (method.upper(), re.sub(r"\{[^}]+\}", "x", path))
        for path, operations in app.openapi()["paths"].items()
        if path.startswith("/api/") and path != "/api/v1/auth/login"
        for method in operations
    ]
    assert len(routes) > 60
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        for method, path in routes:
            response = await client.request(method, path)
            assert response.status_code == 401, (method, path, response.status_code)
            assert response.json()["error_code"] == "UNAUTHENTICATED"


# --- signing in and out ----------------------------------------------------------------------


async def test_the_first_admin_signs_in_and_the_session_identifies_them() -> None:
    async with _client() as client:
        assert await _login(client, *ADMIN) == 200
        me = (await client.get("/api/v1/auth/me")).json()
        assert (me["email"], me["role"]) == (ADMIN[0], "admin")
        assert "password_hash" not in me
        assert (await client.post("/api/v1/auth/logout")).status_code == 204
        assert (await client.get("/api/v1/auth/me")).status_code == 401


async def test_the_session_cookie_is_httponly() -> None:
    async with _client() as client:
        response = await client.post(
            "/api/v1/auth/login", json={"email": ADMIN[0], "password": ADMIN[1]}
        )
    cookie = response.headers["set-cookie"].lower()
    assert "jarvis_session=" in cookie and "httponly" in cookie and "samesite=lax" in cookie


async def test_wrong_password_and_unknown_email_look_the_same_and_are_throttled() -> None:
    async with _client() as client:
        wrong = await client.post(
            "/api/v1/auth/login", json={"email": ADMIN[0], "password": "nope"}
        )
        unknown = await client.post(
            "/api/v1/auth/login", json={"email": "who@x.test", "password": "nope"}
        )
        assert wrong.json()["error_code"] == unknown.json()["error_code"] == "INVALID_CREDENTIALS"
        for _ in range(5):
            await _login(client, ADMIN[0], "nope")
        assert await _login(client, *ADMIN) == 429  # locked even with the right password


async def test_the_audit_actor_is_the_signed_in_user_not_a_chosen_header() -> None:
    async with _client() as client:
        await _login(client, *ADMIN)
        await client.post(
            "/api/v1/cases", json={"title": "Spoof check"}, headers={"X-Jarvis-User": "mallory"}
        )
        body = (await client.get("/api/v1/audit", params={"target": "cases"})).json()
    entries = body["entries"] if isinstance(body, dict) else body
    actors = {e["actor"] for e in entries}
    assert ADMIN[0] in actors and "mallory" not in actors


# --- accounts --------------------------------------------------------------------------------


async def test_an_admin_manages_accounts_and_roles_are_enforced() -> None:
    viewer_body = {"email": "v@tessera.test", "role": "viewer", "password": "Viewer-pass-123"}
    async with _client() as admin:
        await _login(admin, *ADMIN)
        weak = await admin.post("/api/v1/auth/users", json={**viewer_body, "password": "weak"})
        assert (weak.status_code, weak.json()["error_code"]) == (422, "WEAK_PASSWORD")
        viewer = await admin.post("/api/v1/auth/users", json=viewer_body)
        assert viewer.status_code == 201
        dup = await admin.post(
            "/api/v1/auth/users", json={**viewer_body, "email": "V@tessera.test"}
        )
        assert dup.json()["error_code"] == "EMAIL_TAKEN"
        me = (await admin.get("/api/v1/auth/me")).json()
        lock = await admin.patch(f"/api/v1/auth/users/{me['user_id']}", json={"role": "viewer"})
        assert lock.json()["error_code"] == "SELF_LOCKOUT"

    async with _client() as v:
        assert await _login(v, "v@tessera.test", "Viewer-pass-123") == 200
        assert (await v.get("/api/v1/missions")).status_code == 200
        refused = await v.post("/api/v1/cases", json={"title": "Not allowed"})
        assert (refused.status_code, refused.json()["error_code"]) == (403, "FORBIDDEN")
        assert (await v.get("/api/v1/auth/users")).status_code == 403

    async with _client() as admin:
        await _login(admin, *ADMIN)
        off = await admin.patch(
            f"/api/v1/auth/users/{viewer.json()['user_id']}", json={"active": False}
        )
        assert off.json()["active"] is False
    async with _client() as v:
        assert await _login(v, "v@tessera.test", "Viewer-pass-123") == 401
