"""Deterministic fixture provider.

`LLM_PROVIDER=echo` runs the entire test suite with no network, no GPU and no secrets. That
matters for two reasons beyond convenience:

1. **CI can run the agent scenarios.** Behaviour tests are worthless if they only run on a
   machine with a model loaded.
2. **It proves the seam is real.** The `LLMProvider` abstraction is only meaningful if
   something other than Ollama actually implements it. This does.

Resolution order for a completion:

1. A response queued for that role by the test
2. A recorded fixture under `.agent/fixtures/llm/`
3. If `synthesize=True`, a minimal instance generated from the requested JSON schema

Synthesis is **opt-in**. By default a missing fixture raises, because a silently-synthesized
response would let a test pass while proving nothing about the prompt it was supposed to
exercise.
"""

from __future__ import annotations

import hashlib
import json
import re
from collections import deque
from pathlib import Path
from typing import Any

from app.core.config import get_settings
from app.llm.errors import LLMError
from app.llm.provider import CompletionRequest, CompletionResponse, EmbeddingResponse


class NoFixtureError(LLMError):
    """No recorded response for this call, and synthesis is off."""


def fixture_key(role: str, prompt: str) -> str:
    """Stable id for a (role, prompt) pair. Same prompt always resolves to the same file."""
    digest = hashlib.sha256(prompt.encode("utf-8")).hexdigest()[:16]
    return f"{role}_{digest}"


class EchoProvider:
    """Serves recorded or synthesized responses. Never touches the network."""

    def __init__(
        self,
        *,
        model_id: str = "echo",
        responses: dict[str, list[str]] | None = None,
        fixture_dir: Path | None = None,
        synthesize: bool = False,
        embedding_dim: int | None = None,
    ) -> None:
        settings = get_settings()
        self._model_id = model_id
        self._queues: dict[str, deque[str]] = {
            role: deque(texts) for role, texts in (responses or {}).items()
        }
        self._fixture_dir = fixture_dir or (settings.agent_dir / "fixtures" / "llm")
        self._synthesize = synthesize
        self._embedding_dim = embedding_dim or settings.embedding_dim
        self.calls: list[CompletionRequest] = []

    @property
    def model_id(self) -> str:
        return self._model_id

    def queue(self, role: str, *texts: str) -> None:
        """Queue responses for a role. Consumed in order; the last one repeats."""
        self._queues.setdefault(role, deque()).extend(texts)

    async def complete(self, request: CompletionRequest) -> CompletionResponse:
        self.calls.append(request)
        text = self._resolve(request)
        return CompletionResponse(
            text=text,
            model=self._model_id,
            role=request.role,
            prompt_tokens=len(request.prompt) // 4,
            completion_tokens=len(text) // 4,
            latency_ms=0,
            finish_reason="stop",
        )

    async def embed(self, texts: list[str]) -> EmbeddingResponse:
        """Deterministic pseudo-embeddings.

        Derived from a hash of the text, so identical text always yields an identical vector
        and similarity comparisons in tests are reproducible. These carry no semantic
        meaning and must never be used to judge retrieval quality.
        """
        vectors: list[list[float]] = []
        for text in texts:
            seed = hashlib.sha256(text.encode("utf-8")).digest()
            vector = [
                ((seed[i % len(seed)] / 255.0) * 2.0) - 1.0 for i in range(self._embedding_dim)
            ]
            vectors.append(vector)
        return EmbeddingResponse(vectors=vectors, model=f"{self._model_id}-embed")

    async def health(self) -> bool:
        return True

    # --- resolution ------------------------------------------------------------

    def _resolve(self, request: CompletionRequest) -> str:
        queued = self._queues.get(request.role)
        if queued:
            # The last queued response repeats, so a test does not have to count calls.
            return queued.popleft() if len(queued) > 1 else queued[0]

        path = self._fixture_dir / f"{fixture_key(request.role, request.prompt)}.json"
        if path.exists():
            return path.read_text(encoding="utf-8")

        if self._synthesize and request.schema_hint:
            return json.dumps(synthesize_from_schema(json.loads(request.schema_hint)))

        raise NoFixtureError(
            f"no fixture for role '{request.role}' (looked in {path.name}); "
            "queue a response, record a fixture, or construct EchoProvider(synthesize=True)"
        )


# --- schema synthesis ----------------------------------------------------------

# Regex fragments this generator understands. Anything else falls back to a plain string,
# which may then fail validation - deliberately, since a silently wrong value would be
# worse than a loud failure.
_PATTERN_PARTS = re.compile(r"\\d\{(\d+),?\d*\}|\[0-9a-f\]\{(\d+)\}|([^\\\[\]{}^$]+)")


def _string_matching(pattern: str) -> str:
    """Build a minimal string satisfying a simple anchored pattern.

    Covers the identifier patterns this project uses (`^task_\\d{3,}$`, `^F-\\d{3,}$`,
    `^run_[0-9a-f]{12}$`). Not a general regex solver, and does not pretend to be.
    """
    body = pattern.removeprefix("^").removesuffix("$")
    out: list[str] = []
    for digits, hexes, literal in _PATTERN_PARTS.findall(body):
        if digits:
            out.append("1" * int(digits))
        elif hexes:
            out.append("a" * int(hexes))
        elif literal:
            out.append(literal)
    return "".join(out) or "x"


def synthesize_from_schema(schema: dict[str, Any], defs: dict[str, Any] | None = None) -> Any:
    """Produce a minimal instance satisfying a Pydantic-generated JSON Schema.

    Minimal on purpose: required fields only, shortest valid values. The point is to give
    the structured-output machinery something schema-valid to parse, not to fabricate
    plausible agent output.
    """
    defs = defs if defs is not None else schema.get("$defs", {})

    if "$ref" in schema:
        ref = str(schema["$ref"]).rsplit("/", 1)[-1]
        return synthesize_from_schema(defs.get(ref, {}), defs)

    if "const" in schema:
        return schema["const"]
    if schema.get("enum"):
        return schema["enum"][0]
    if "default" in schema:
        return schema["default"]

    for key in ("anyOf", "oneOf", "allOf"):
        if key in schema:
            options = [o for o in schema[key] if o.get("type") != "null"] or schema[key]
            return synthesize_from_schema(options[0], defs)

    schema_type = schema.get("type")

    if schema_type == "object" or "properties" in schema:
        props: dict[str, Any] = schema.get("properties", {})
        required: list[str] = schema.get("required", list(props))
        return {
            name: synthesize_from_schema(props[name], defs) for name in required if name in props
        }

    if schema_type == "array":
        min_items = int(schema.get("minItems", 0))
        item_schema = schema.get("items", {})
        return [synthesize_from_schema(item_schema, defs) for _ in range(max(min_items, 0))]

    if schema_type == "string":
        if "pattern" in schema:
            return _string_matching(str(schema["pattern"]))
        if schema.get("format") == "date-time":
            return "2026-01-01T00:00:00Z"
        return "x" * max(int(schema.get("minLength", 1)), 1)

    if schema_type == "integer":
        return int(schema.get("minimum", schema.get("exclusiveMinimum", 0) or 0))
    if schema_type == "number":
        return float(schema.get("minimum", schema.get("exclusiveMinimum", 0) or 0))
    if schema_type == "boolean":
        return False
    if schema_type == "null":
        return None

    return {}
