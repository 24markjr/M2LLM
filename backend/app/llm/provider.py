"""The provider protocol — the only door to a language model.

Invariant #1: no module outside this package may call a model directly. Enforced by
`tests/unit/test_llm_isolation.py`, which fails if any other module imports httpx or
references `OLLAMA_*`.

That test is what turns "the LLM is a component, not the architecture" from a claim into a
checkable property.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from pydantic import Field

from app.schemas.common import JarvisModel, NonEmptyStr


class CompletionRequest(JarvisModel):
    """One model call.

    `role` is how a caller names its purpose (`intent`, `planner`, `reasoning`). Generation
    parameters come from `models.yaml` via that role, so no engine ever names a model.
    """

    prompt: NonEmptyStr
    system: str = ""
    role: str = "default"
    temperature: float = Field(default=0.0, ge=0.0, le=2.0)
    seed: int = 42
    top_p: float = Field(default=0.9, gt=0.0, le=1.0)
    max_tokens: int = Field(default=2048, ge=1)
    # Ask the provider to constrain output to JSON, where it can.
    json_mode: bool = False
    # Reasoning models (qwen3 among them) emit a deliberation pass before answering.
    # Off by default: it consumes the token budget, slows every evaluation run, and is
    # exactly the content invariant #3 keeps out of the record. See ADR-003.
    think: bool = False
    # JSON Schema injected into the prompt by `generate_structured`.
    schema_hint: str = ""
    stop: list[str] = Field(default_factory=list)


class CompletionResponse(JarvisModel):
    """What came back, plus what it cost."""

    text: str
    model: str
    role: str = "default"
    prompt_tokens: int = Field(default=0, ge=0)
    completion_tokens: int = Field(default=0, ge=0)
    latency_ms: int = Field(default=0, ge=0)
    finish_reason: str = ""

    @property
    def total_tokens(self) -> int:
        return self.prompt_tokens + self.completion_tokens


class EmbeddingResponse(JarvisModel):
    vectors: list[list[float]]
    model: str
    latency_ms: int = Field(default=0, ge=0)

    @property
    def dimensions(self) -> int:
        return len(self.vectors[0]) if self.vectors else 0


@runtime_checkable
class LLMProvider(Protocol):
    """Everything the system needs from a language model.

    Deliberately small. A provider that can complete and embed is enough for every engine in
    the project; anything larger would leak provider-specific capability into the seam and
    make swapping one out a refactor instead of a config change.
    """

    @property
    def model_id(self) -> str: ...

    async def complete(self, request: CompletionRequest) -> CompletionResponse: ...

    async def embed(self, texts: list[str]) -> EmbeddingResponse: ...

    async def health(self) -> bool: ...
