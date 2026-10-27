"""Every `/api/` request is signed in and permitted, or refused (v4 Phase 1a).

One check in front of every route, rather than a dependency on each, so a new route cannot be added
unprotected. A signed-in request has its `X-Jarvis-User` header replaced by the user's email: the
existing routes and the audit log read the actor from that header, and before accounts any caller
could have set it to anyone.
"""

from __future__ import annotations

from typing import Any

from fastapi import Request, status
from fastapi.responses import JSONResponse

from app.auth.permissions import allowed
from app.auth.ratelimit import over_limit
from app.auth.service import COOKIE, get_auth_store, public, user_for
from app.auth.tenancy import set_org
from app.core.config import get_settings

PUBLIC = {"/health", "/api/v1/auth/login"}
PROTECTED_DOCS = {"/docs", "/openapi.json", "/redoc"}


def _refuse(code: int, error_code: str, message: str) -> JSONResponse:
    return JSONResponse(
        status_code=code,
        content={"error_code": error_code, "message": message, "run_id": None, "details": {}},
    )


async def require_auth(request: Request, call_next: Any) -> Any:
    path = request.url.path
    if (
        not get_settings().auth_required
        or request.method == "OPTIONS"  # CORS preflight carries no cookie
        or path in PUBLIC
        or not (path.startswith("/api/") or path in PROTECTED_DOCS)
    ):
        return await call_next(request)

    token = request.cookies.get(COOKIE, "")
    user = await user_for(await get_auth_store(), token) if token else None
    if user is None:
        return _refuse(status.HTTP_401_UNAUTHORIZED, "UNAUTHENTICATED", "sign in first")
    if not allowed(user.role, request.method, path):
        return _refuse(
            status.HTTP_403_FORBIDDEN,
            "FORBIDDEN",
            f"a {user.role.value} may not {request.method} {path}",
        )

    if over_limit(user.user_id, write=request.method not in {"GET", "HEAD"}):
        response = _refuse(
            status.HTTP_429_TOO_MANY_REQUESTS,
            "RATE_LIMITED",
            "too many requests from this account; wait a minute and try again",
        )
        response.headers["Retry-After"] = "60"
        return response

    headers = [(k, v) for k, v in request.scope["headers"] if k.lower() != b"x-jarvis-user"]
    headers.append((b"x-jarvis-user", user.email.encode("utf-8")))
    request.scope["headers"] = headers
    request.state.user = public(user)
    # Everything this request reads or creates is the user's organisation's (v4 Phase 1c).
    set_org(user.org_id)
    return await call_next(request)
