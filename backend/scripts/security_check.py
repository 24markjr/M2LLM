"""A scripted attack on a running JARVIS (v4 Phase 8): what an outsider - or a signed-in user of
another organisation - can reach. Not a substitute for an independent penetration test; it is the
part of one that can be re-run before every release.

    python scripts/security_check.py https://8.231.91.94.sslip.io
    JARVIS_EMAIL=... JARVIS_PASSWORD=... python scripts/security_check.py https://...  # signed in

Checks:
 1. HTTP redirects to HTTPS; the certificate verifies.
 2. Security headers: HSTS, nosniff, frame denial, CSP on the console, no Server banner.
 3. Every API route in docs/openapi.json refuses an anonymous caller (401), the docs included.
 4. Repeated failed sign-ins for one email are throttled (429).
 5. Only 80 and 443 are open: SSH, Postgres, Neo4j, the backend and the model port refuse.
 6. Signed in: a mission naming a server file by path reads nothing (/proc/self/environ, ../).
Exit code 1 if any check fails.
"""

from __future__ import annotations

import json
import os
import re
import secrets
import socket
import sys
from pathlib import Path
from urllib.parse import urlparse

import httpx

OPENAPI = Path(__file__).resolve().parents[2] / "docs" / "openapi.json"
PUBLIC = {"/health", "/health/live", "/api/v1/auth/login"}
results: list[tuple[str, bool, str]] = []


def check(name: str, ok: bool, detail: str = "") -> None:
    results.append((name, ok, detail))
    print(f"{'PASS' if ok else 'FAIL'}  {name}" + (f"  - {detail}" if detail else ""))


def main(base: str) -> int:
    base = base.rstrip("/")
    host = urlparse(base).hostname or ""
    client = httpx.Client(timeout=20, follow_redirects=False)

    # 1. Transport.
    plain = client.get(base.replace("https://", "http://") + "/")
    check(
        "HTTP redirects to HTTPS",
        plain.status_code in (301, 308)
        and plain.headers.get("location", "").startswith("https://"),
        str(plain.status_code),
    )
    try:
        page = client.get(base + "/")
        check("the certificate verifies", True)
    except httpx.ConnectError as exc:
        check("the certificate verifies", False, str(exc))
        return 1

    # 2. Headers.
    h = page.headers
    check("HSTS", "max-age=" in h.get("strict-transport-security", ""))
    check("nosniff", h.get("x-content-type-options") == "nosniff")
    check("frames denied", h.get("x-frame-options") == "DENY")
    csp = h.get("content-security-policy", "")
    check("CSP on the console", "default-src 'self'" in csp and "frame-ancestors 'none'" in csp)
    check("no Server banner", "server" not in h)

    # 3. Every API route refuses an anonymous caller.
    paths = json.loads(OPENAPI.read_text(encoding="utf-8"))["paths"]
    open_routes = []
    for path, methods in paths.items():
        if path in PUBLIC:
            continue
        concrete = re.sub(r"\{[^}]+\}", "x", path)
        for method in methods:
            response = client.request(method.upper(), base + concrete, json={})
            if response.status_code != 401:
                open_routes.append(f"{method.upper()} {path} -> {response.status_code}")
    check(
        f"{sum(len(m) for p, m in paths.items() if p not in PUBLIC)} API routes refuse anonymous",
        not open_routes,
        "; ".join(open_routes[:5]),
    )
    for doc in ("/docs", "/openapi.json"):
        check(f"{doc} needs sign-in", client.get(base + doc).status_code == 401)

    # 4. Sign-in throttling, on an address that has no account.
    probe = f"probe-{secrets.token_hex(4)}@example.invalid"
    codes = [
        client.post(base + "/api/v1/auth/login", json={"email": probe, "password": "x"}).status_code
        for _ in range(6)
    ]
    check("failed sign-ins are throttled", codes[-1] == 429 and set(codes[:5]) == {401}, str(codes))

    # 5. Ports.
    for port, what in (
        (22, "SSH"),
        (5432, "Postgres"),
        (7687, "Neo4j"),
        (8000, "backend"),
        (11434, "model"),
    ):
        try:
            with socket.create_connection((host, port), timeout=4):
                check(f"port {port} ({what}) closed", False, "open")
        except OSError:
            check(f"port {port} ({what}) closed", True)

    # 6. Signed in: no file read by path.
    email, password = os.environ.get("JARVIS_EMAIL"), os.environ.get("JARVIS_PASSWORD")
    if email and password:
        session = httpx.Client(timeout=60, base_url=base)
        signed = session.post("/api/v1/auth/login", json={"email": email, "password": password})
        check(
            "signed in for the signed-in checks", signed.status_code == 200, str(signed.status_code)
        )
        for name in ("/proc/self/environ", "../uploads/x.txt", "/etc/hosts"):
            response = session.post(
                "/api/v1/missions", json={"objective": "Read this file.", "documents": [name]}
            )
            check(
                f"a mission cannot read {name}",
                response.status_code == 422,
                str(response.status_code),
            )
    else:
        print("SKIP  signed-in checks (set JARVIS_EMAIL and JARVIS_PASSWORD)")

    failed = [r for r in results if not r[1]]
    print(f"\n{len(results) - len(failed)} passed, {len(failed)} failed")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1] if len(sys.argv) > 1 else "https://8.231.91.94.sslip.io"))
