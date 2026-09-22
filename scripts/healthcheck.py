"""Phase 0 environment healthcheck.

Verifies the three things every later phase assumes:

  1. PostgreSQL is reachable and answers `SELECT 1`
  2. The `vector` extension is present (or installable) in that database
  3. The configured LLM provider answers, and serves the configured model

Run:  python scripts/healthcheck.py  [--json]

Exit code 0 = all required checks passed. 1 = at least one failed.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from dataclasses import dataclass, field
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "backend"))

from app.core.config import LLMProviderName, Settings, get_settings  # noqa: E402

OK = "PASS"
FAIL = "FAIL"
SKIP = "SKIP"


@dataclass
class Check:
    name: str
    status: str = FAIL
    detail: str = ""
    required: bool = True
    hint: str = ""


@dataclass
class Report:
    checks: list[Check] = field(default_factory=list)

    def add(self, check: Check) -> Check:
        self.checks.append(check)
        return check

    @property
    def ok(self) -> bool:
        return all(c.status != FAIL for c in self.checks if c.required)


async def check_postgres(settings: Settings, report: Report) -> None:
    conn_check = report.add(
        Check(
            "postgres:connect",
            hint="docker compose up -d postgres",
        )
    )
    vector_check = report.add(
        Check(
            "postgres:vector-extension",
            hint="image must be pgvector/pgvector:pg16",
        )
    )

    try:
        import asyncpg
    except ImportError:
        conn_check.detail = "asyncpg not installed"
        conn_check.hint = 'pip install -e "backend[dev]"'
        vector_check.status = SKIP
        return

    dsn = settings.sync_database_url.replace("postgresql+asyncpg", "postgresql")
    try:
        conn = await asyncio.wait_for(asyncpg.connect(dsn), timeout=10)
    except Exception as exc:  # noqa: BLE001 — a healthcheck reports, it does not raise
        conn_check.detail = f"{type(exc).__name__}: {exc}"
        vector_check.status = SKIP
        vector_check.detail = "skipped: no connection"
        return

    try:
        one = await conn.fetchval("SELECT 1")
        version = await conn.fetchval("SHOW server_version")
        conn_check.status = OK if one == 1 else FAIL
        conn_check.detail = f"PostgreSQL {version}"

        available = await conn.fetchval(
            "SELECT 1 FROM pg_available_extensions WHERE name = 'vector'"
        )
        if not available:
            vector_check.detail = "extension 'vector' not available in this image"
            return
        await conn.execute("CREATE EXTENSION IF NOT EXISTS vector")
        installed = await conn.fetchval(
            "SELECT extversion FROM pg_extension WHERE extname = 'vector'"
        )
        vector_check.status = OK
        vector_check.detail = f"vector {installed}"
    except Exception as exc:  # noqa: BLE001
        vector_check.detail = f"{type(exc).__name__}: {exc}"
    finally:
        await conn.close()


async def check_llm(settings: Settings, report: Report) -> None:
    reach = report.add(
        Check(
            f"llm:{settings.llm_provider.value}:reachable",
            hint="install Ollama and run `ollama serve`",
        )
    )
    model = report.add(
        Check(
            f"llm:{settings.llm_provider.value}:model",
            hint=f"ollama pull {settings.ollama_model}",
        )
    )

    if settings.llm_provider is LLMProviderName.ECHO:
        reach.status = OK
        reach.detail = "echo provider - no network dependency"
        model.status = OK
        model.detail = "echo provider serves deterministic fixtures"
        return

    try:
        import httpx
    except ImportError:
        reach.detail = "httpx not installed"
        reach.hint = 'pip install -e "backend[dev]"'
        model.status = SKIP
        return

    url = settings.ollama_base_url.rstrip("/") + "/api/tags"
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.get(url)
            resp.raise_for_status()
            payload = resp.json()
    except Exception as exc:  # noqa: BLE001
        reach.detail = f"{type(exc).__name__}: {exc} ({url})"
        model.status = SKIP
        model.detail = "skipped: provider unreachable"
        return

    names = [m.get("name", "") for m in payload.get("models", [])]
    reach.status = OK
    reach.detail = f"{len(names)} model(s) available"

    wanted = settings.ollama_model
    # Ollama reports tagged names ("qwen3:8b"); match the bare name too.
    if any(n == wanted or n.split(":")[0] == wanted.split(":")[0] for n in names):
        model.status = OK
        model.detail = f"'{wanted}' present"
    else:
        model.detail = f"'{wanted}' not pulled; available: {', '.join(names) or 'none'}"


def check_config(settings: Settings, report: Report) -> None:
    c = report.add(Check("config:load"))
    c.status = OK
    c.detail = (
        f"env={settings.app_env} provider={settings.llm_provider.value} "
        f"model={settings.ollama_model} replan_max={settings.max_replan_iterations}"
    )

    env_file = report.add(
        Check(
            "config:.env",
            required=False,
            hint="copy .env.example to .env",
        )
    )
    if (REPO_ROOT / ".env").exists():
        env_file.status = OK
        env_file.detail = "present"
    else:
        env_file.status = SKIP
        env_file.detail = "not found - using .env.example defaults"


def render(report: Report) -> None:
    # The Windows console defaults to cp1252, which cannot encode arrows or dashes.
    # Operator output stays ASCII-only rather than depending on the active code page.
    width = max(len(c.name) for c in report.checks) + 2
    print("\nJARVIS environment healthcheck")
    print("-" * (width + 40))
    for c in report.checks:
        mark = {OK: "  OK  ", FAIL: " FAIL ", SKIP: " SKIP "}[c.status]
        print(f"[{mark}] {c.name:<{width}} {c.detail}")
        if c.status == FAIL and c.hint:
            print(f"{'':>{width + 9}}-> {c.hint}")
    print("-" * (width + 40))
    print("RESULT:", "ALL GREEN" if report.ok else "ACTION REQUIRED", "\n")


async def main() -> int:
    parser = argparse.ArgumentParser(description="JARVIS environment healthcheck")
    parser.add_argument("--json", action="store_true", help="machine-readable output")
    args = parser.parse_args()

    settings = get_settings()
    report = Report()

    check_config(settings, report)
    await check_postgres(settings, report)
    await check_llm(settings, report)

    if args.json:
        print(
            json.dumps(
                {
                    "ok": report.ok,
                    "checks": [
                        {
                            "name": c.name,
                            "status": c.status,
                            "detail": c.detail,
                            "required": c.required,
                        }
                        for c in report.checks
                    ],
                },
                indent=2,
            )
        )
    else:
        render(report)

    return 0 if report.ok else 1


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
