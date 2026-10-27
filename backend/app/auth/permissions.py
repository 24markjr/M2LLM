"""Who may call what (Phase 1a): one matrix, checked for every `/api/` request by the middleware.

Rules, from least to most:
- **viewer** - reads only (GET, plus the read-only searches that happen to be POSTs)
- **reviewer** - a viewer who may also review and challenge findings
- **analyst** - everything except the admin-only routes
- **admin** - everything

Kept as data, and tested route by route, so a new write route is refused to viewers by default
rather than allowed by omission.
"""

from __future__ import annotations

import re

from app.auth.models import Role

READ_METHODS = {"GET", "HEAD", "OPTIONS"}

# POST routes that only read: searching is not changing anything.
_READ_POSTS = [re.compile(p) for p in (r"^/api/v1/context/retrieve$",)]

# What a reviewer may write on top of reading.
_REVIEWER_WRITES = [
    re.compile(p)
    for p in (
        r"^/api/v1/missions/[^/]+/findings/[^/]+/review$",
        r"^/api/v1/missions/[^/]+/findings/[^/]+/challenge$",
    )
]

# Only an admin: accounts, and the bulk deletions.
_ADMIN_ONLY = [
    (None, re.compile(r"^/api/v1/auth/(users|organisations)")),
    ("DELETE", re.compile(r"^/api/v1/missions$")),
    ("DELETE", re.compile(r"^/api/v1/recordings$")),
]

# Every signed-in user may manage their own session, whatever their role.
_SELF = [re.compile(p) for p in (r"^/api/v1/auth/(me|logout|password)$",)]


def allowed(role: Role, method: str, path: str) -> bool:
    method = method.upper()
    if any(p.match(path) for p in _SELF):
        return True
    if any((m is None or m == method) and p.match(path) for m, p in _ADMIN_ONLY):
        return role is Role.ADMIN
    if role in (Role.ADMIN, Role.ANALYST):
        return True
    if method in READ_METHODS or (method == "POST" and any(p.match(path) for p in _READ_POSTS)):
        return True
    return (
        role is Role.REVIEWER and method == "POST" and any(p.match(path) for p in _REVIEWER_WRITES)
    )
