"""Prompt loading.

Prompts live in `.agent/prompts/*.md`, never as Python string literals. A prompt is the
behavioural surface of an LLM-driven system: buried in code, a change to one is invisible in
review, untracked in evaluation, and impossible to attribute a metric shift to. As a file, a
prompt change is a diff, and every evaluation report stamps the version it ran against.

File format:

    ---
    role: intent
    version: 1
    output_schema: app.schemas.intent.Intent
    phase: 6
    ---

    ## Inputs
    ...

Variables are `{{name}}`. Substitution is strict — an unfilled placeholder raises rather
than reaching the model as literal `{{name}}`, which is the kind of defect that produces
confidently wrong output instead of an error.
"""

from __future__ import annotations

import re
from pathlib import Path

import yaml
from pydantic import Field

from app.core.config import get_settings
from app.llm.errors import PromptNotFoundError
from app.schemas.common import JarvisModel, NonEmptyStr

_FRONT_MATTER = re.compile(r"\A---\s*\n(.*?)\n---\s*\n", re.DOTALL)
_PLACEHOLDER = re.compile(r"\{\{\s*(\w+)\s*\}\}")


class PromptAsset(JarvisModel):
    """One loaded prompt."""

    role: NonEmptyStr
    version: int = Field(default=1, ge=1)
    body: NonEmptyStr
    output_schema: str = ""
    phase: int = 0
    path: str = ""

    @property
    def variables(self) -> set[str]:
        return set(_PLACEHOLDER.findall(self.body))

    def render(self, **values: object) -> str:
        """Fill placeholders, refusing to leave any unfilled.

        A prompt reaching the model with a literal `{{document_text}}` in it would produce
        confidently wrong output rather than an error, so this is strict on purpose.
        """
        missing = self.variables - set(values)
        if missing:
            raise KeyError(f"prompt '{self.role}' is missing values for: {sorted(missing)}")

        def _replace(match: re.Match[str]) -> str:
            return str(values[match.group(1)])

        return _PLACEHOLDER.sub(_replace, self.body)


class PromptLibrary:
    """Loads and caches prompt assets from `.agent/prompts/`."""

    def __init__(self, directory: Path | None = None) -> None:
        self.directory = directory or (get_settings().agent_dir / "prompts")
        self._cache: dict[str, PromptAsset] = {}

    def get(self, role: str) -> PromptAsset:
        if role in self._cache:
            return self._cache[role]

        path = self.directory / f"{role}.md"
        if not path.exists():
            raise PromptNotFoundError(
                f"no prompt for role '{role}' at {path}. Prompts are versioned assets - "
                "add the file rather than inlining the text at the call site."
            )

        asset = self._parse(path, role)
        self._cache[role] = asset
        return asset

    def available(self) -> list[str]:
        if not self.directory.exists():
            return []
        return sorted(p.stem for p in self.directory.glob("*.md") if p.stem != "README")

    def versions(self) -> dict[str, int]:
        """Prompt versions, for stamping evaluation reports and traces.

        Only loaded prompts are reported: a run's stamp should describe what it actually
        used, not what happened to be on disk.
        """
        return {role: asset.version for role, asset in self._cache.items()}

    def clear(self) -> None:
        self._cache.clear()

    @staticmethod
    def _parse(path: Path, role: str) -> PromptAsset:
        text = path.read_text(encoding="utf-8")
        match = _FRONT_MATTER.match(text)

        meta: dict[str, object] = {}
        body = text
        if match:
            parsed = yaml.safe_load(match.group(1))
            if isinstance(parsed, dict):
                meta = parsed
            body = text[match.end() :]

        return PromptAsset(
            role=str(meta.get("role", role)),
            version=int(meta.get("version", 1)),  # type: ignore[call-overload]
            body=body.strip(),
            output_schema=str(meta.get("output_schema", "")),
            phase=int(meta.get("phase", 0)),  # type: ignore[call-overload]
            path=str(path),
        )


_library: PromptLibrary | None = None


def get_prompt_library() -> PromptLibrary:
    global _library
    if _library is None:
        _library = PromptLibrary()
    return _library
