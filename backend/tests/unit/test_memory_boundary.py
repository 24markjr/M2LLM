"""Phase 33: memory is never read back into a run (invariant 4, rule 8).

A run that silently used facts from an earlier run could not be reconstructed from its own events,
and its evaluation numbers would depend on the order scenarios ran in. So the code a run executes
must not be able to reach memory at all, and that is checked here on the source, not trusted.
"""

from __future__ import annotations

import ast
from pathlib import Path

import app

APP = Path(app.__file__).parent

# Everything a mission executes: planning, tools, reasoning, verification, the model client, and
# the stores a run writes its knowledge to.
RUN_PACKAGES = (
    "orchestration",
    "intelligence",
    "tools",
    "llm",
    "security",
    "evaluation",
    "integrations",
)


def _imports(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    found: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            found.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            found.add(node.module)
    return found


def test_nothing_a_run_executes_imports_memory() -> None:
    offenders = [
        str(path.relative_to(APP))
        for package in RUN_PACKAGES
        for path in (APP / package).rglob("*.py")
        if any(m == "app.memory" or m.startswith("app.memory.") for m in _imports(path))
    ]
    assert offenders == []


def test_memory_is_reached_only_from_the_api() -> None:
    users = sorted(
        str(path.relative_to(APP)).replace("\\", "/")
        for path in APP.rglob("*.py")
        if not str(path.relative_to(APP)).startswith("memory")
        and any(m == "app.memory" or m.startswith("app.memory.") for m in _imports(path))
    )
    assert users == [
        "api/registry.py",
        "api/v1/memory.py",
    ]
