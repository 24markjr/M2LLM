"""Invariant #1 — the LLM is a component inside the system, not the architecture.

This is the test that makes that claim checkable rather than rhetorical. If a future engine
takes a shortcut and calls the model directly, this fails.

Also guards the specification's "must not do" list: no `eval`, no `exec`, no arbitrary code
execution anywhere in the application.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

APP_ROOT = Path(__file__).resolve().parents[2] / "app"

# The only package allowed to speak to a model server.
LLM_PACKAGE = APP_ROOT / "llm"

# Integration adapters legitimately make HTTP calls to other members' services.
INTEGRATION_PACKAGE = APP_ROOT / "integrations"

FORBIDDEN_IMPORTS = {"httpx", "requests", "aiohttp", "urllib.request", "ollama", "openai"}


def _python_files(root: Path) -> list[Path]:
    return sorted(p for p in root.rglob("*.py") if "__pycache__" not in p.parts)


def _module_imports(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    found: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            found.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            found.add(node.module)
    return found


def _outside_llm() -> list[Path]:
    return [
        p
        for p in _python_files(APP_ROOT)
        if LLM_PACKAGE not in p.parents and INTEGRATION_PACKAGE not in p.parents
    ]


def test_no_http_client_outside_the_llm_and_integration_packages() -> None:
    offenders: list[str] = []
    for path in _outside_llm():
        imports = _module_imports(path)
        hits = {i for i in imports if i.split(".")[0] in FORBIDDEN_IMPORTS}
        if hits:
            offenders.append(f"{path.relative_to(APP_ROOT)}: {sorted(hits)}")

    assert not offenders, (
        "modules outside app/llm/ must reach the model through LLMProvider:\n"
        + "\n".join(offenders)
    )


def test_no_module_outside_config_reads_ollama_settings_directly() -> None:
    """A model name appearing at a call site would break ADR-003's swappability."""
    offenders: list[str] = []
    for path in _python_files(APP_ROOT):
        if path.name == "config.py":
            continue
        text = path.read_text(encoding="utf-8")
        for line in text.splitlines():
            stripped = line.strip()
            # Comments and docstrings may legitimately mention the variable.
            if stripped.startswith("#"):
                continue
            if "OLLAMA_" in line and "os.environ" in line:
                offenders.append(f"{path.relative_to(APP_ROOT)}: {stripped}")

    assert not offenders, "environment access belongs in Settings:\n" + "\n".join(offenders)


def test_no_environment_access_outside_config() -> None:
    """Invariant #7: nothing reads os.environ directly."""
    offenders: list[str] = []
    for path in _python_files(APP_ROOT):
        if path.name == "config.py":
            continue
        imports = _module_imports(path)
        text = path.read_text(encoding="utf-8")
        if "os.environ" in text or "os.getenv" in text or "getenv" in imports:
            offenders.append(str(path.relative_to(APP_ROOT)))

    assert not offenders, "configuration must come from Settings, not os.environ:\n" + "\n".join(
        offenders
    )


@pytest.mark.parametrize("forbidden", ["eval", "exec", "compile", "__import__"])
def test_no_dynamic_code_execution_anywhere(forbidden: str) -> None:
    """The specification's 'no arbitrary code execution' rule, enforced structurally.

    The calculator tool (Phase 9) parses with `ast.parse` and walks a node whitelist. If a
    shortcut is ever taken there, this test fails.
    """
    offenders: list[str] = []
    for path in _python_files(APP_ROOT):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if (
                isinstance(node, ast.Call)
                and isinstance(node.func, ast.Name)
                and node.func.id == forbidden
            ):
                offenders.append(f"{path.relative_to(APP_ROOT)}:{node.lineno}")

    assert not offenders, f"{forbidden}() is forbidden:\n" + "\n".join(offenders)


def test_schemas_import_nothing_from_the_application() -> None:
    """The typed spine must stay a contract, not a consequence of the implementation."""
    offenders: list[str] = []
    for path in _python_files(APP_ROOT / "schemas"):
        for imported in _module_imports(path):
            if imported.startswith("app.") and not imported.startswith("app.schemas"):
                offenders.append(f"{path.relative_to(APP_ROOT)}: {imported}")

    assert not offenders, "app/schemas must not depend on engines:\n" + "\n".join(offenders)


def test_the_llm_package_does_not_import_engines() -> None:
    """Layering: llm sits below intelligence and must never reach up into it."""
    offenders: list[str] = []
    for path in _python_files(LLM_PACKAGE):
        for imported in _module_imports(path):
            if imported.startswith("app.intelligence") or imported.startswith("app.tools"):
                offenders.append(f"{path.relative_to(APP_ROOT)}: {imported}")

    assert not offenders, "app/llm must not import engines:\n" + "\n".join(offenders)
