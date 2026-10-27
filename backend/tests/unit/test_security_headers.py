"""v4 Phase 8: the console's Content-Security-Policy allows its one inline script by hash.

Edit the theme script in frontend/index.html and this fails until the hash in deploy/Caddyfile is
updated - otherwise the page would silently stop applying the dark theme in production.
"""

from __future__ import annotations

import base64
import hashlib
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]


def test_the_csp_allows_exactly_the_inline_scripts_of_the_console() -> None:
    html = (ROOT / "frontend" / "index.html").read_text(encoding="utf-8")
    caddy = (ROOT / "deploy" / "Caddyfile").read_text(encoding="utf-8")
    policy = next(line for line in caddy.splitlines() if "Content-Security-Policy" in line)
    for script in re.findall(r"<script>(.*?)</script>", html, re.S):
        digest = base64.b64encode(hashlib.sha256(script.encode("utf-8")).digest()).decode()
        assert f"'sha256-{digest}'" in policy
    assert "'unsafe-inline'" not in policy.split("script-src", 1)[1].split(";", 1)[0]
    assert "frame-ancestors 'none'" in policy and "object-src 'none'" in policy
