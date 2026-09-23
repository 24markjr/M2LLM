"""Ollama provider — local inference over HTTP.

This is the only module in the project that speaks to a model server. Everything else goes
through `LLMProvider` (invariant #1).
"""

from __future__ import annotations

import json
import time
from typing import Any

import httpx

from app.core.config import get_settings
from app.core.logging import get_logger
from app.llm.errors import ProviderTimeoutError, ProviderUnavailableError
from app.llm.provider import CompletionRequest, CompletionResponse, EmbeddingResponse

log = get_logger(__name__)


class OllamaProvider:
    """Talks to a local Ollama server.

    Connection errors and timeouts are mapped to typed errors carrying a `FailureClass`, so
    the execution engine can tell "retry might work" from "retrying is pointless" without
    inspecting exception text.
    """

    def __init__(
        self,
        base_url: str | None = None,
        model: str | None = None,
        timeout_s: float | None = None,
    ) -> None:
        settings = get_settings()
        self._base_url = (base_url or settings.ollama_base_url).rstrip("/")
        self._model = model or settings.ollama_model
        self._timeout_s = timeout_s or settings.ollama_timeout_s
        self._embedding_model = settings.embedding_model

    @property
    def model_id(self) -> str:
        return self._model

    async def complete(self, request: CompletionRequest) -> CompletionResponse:
        options: dict[str, Any] = {
            "temperature": request.temperature,
            "top_p": request.top_p,
            "num_predict": request.max_tokens,
            "seed": request.seed,
        }
        if request.stop:
            options["stop"] = request.stop

        # Constrained decoding where the provider supports it. Ollama accepts a JSON Schema
        # as `format` and restricts generation to it, which is strictly better than pasting
        # the schema into the prompt and hoping: the model then cannot echo the schema back,
        # cannot invent a field, and does not spend its token budget reproducing definitions
        # instead of answering.
        #
        # Pasting it was costing whole responses. qwen3:4b returned the schema *and* the
        # data, and with a long observation set that exceeded the token budget, so the JSON
        # arrived truncated and unparseable - which read downstream as "no findings".
        schema: dict[str, Any] | None = None
        if request.schema_hint:
            try:
                schema = json.loads(request.schema_hint)
            except json.JSONDecodeError:
                schema = None

        prompt = request.prompt
        if schema is None and request.schema_hint:
            prompt = f"{prompt}\n\nRespond with JSON only, no commentary and no code fences."

        body: dict[str, Any] = {
            "model": self._model,
            "prompt": prompt,
            "stream": False,
            "options": options,
            # Reasoning models deliberate before answering. Disabled by default: the
            # deliberation consumes the token budget (an empty `response` with
            # done_reason=length), slows every evaluation run, and is precisely the content
            # invariant #3 keeps out of the record.
            "think": request.think,
        }
        if request.system:
            body["system"] = request.system
        if schema is not None:
            body["format"] = schema
        elif request.json_mode:
            body["format"] = "json"

        started = time.perf_counter()
        payload = await self._post("/api/generate", body)
        latency_ms = int((time.perf_counter() - started) * 1000)

        # `payload["thinking"]` is read by nothing, deliberately. A reasoning model's
        # deliberation must not enter the system at all - not the response, not telemetry,
        # not an event payload. Redaction at the event bus is the second line of defence;
        # this is the first.
        return CompletionResponse(
            text=str(payload.get("response", "")),
            model=self._model,
            role=request.role,
            prompt_tokens=int(payload.get("prompt_eval_count", 0)),
            completion_tokens=int(payload.get("eval_count", 0)),
            latency_ms=latency_ms,
            finish_reason=str(payload.get("done_reason", "")),
        )

    async def embed(self, texts: list[str]) -> EmbeddingResponse:
        if not texts:
            return EmbeddingResponse(vectors=[], model=self._embedding_model)

        started = time.perf_counter()
        payload = await self._post("/api/embed", {"model": self._embedding_model, "input": texts})
        latency_ms = int((time.perf_counter() - started) * 1000)

        raw = payload.get("embeddings") or []
        vectors = [[float(x) for x in vec] for vec in raw]
        return EmbeddingResponse(
            vectors=vectors, model=self._embedding_model, latency_ms=latency_ms
        )

    async def health(self) -> bool:
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                resp = await client.get(f"{self._base_url}/api/tags")
                resp.raise_for_status()
                names = [m.get("name", "") for m in resp.json().get("models", [])]
        except (httpx.HTTPError, ValueError):
            return False
        wanted = self._model.split(":")[0]
        return any(n.split(":")[0] == wanted for n in names)

    async def _post(self, path: str, body: dict[str, Any]) -> dict[str, Any]:
        url = f"{self._base_url}{path}"
        try:
            async with httpx.AsyncClient(timeout=self._timeout_s) as client:
                resp = await client.post(url, json=body)
                resp.raise_for_status()
                data: dict[str, Any] = resp.json()
                return data
        except httpx.TimeoutException as exc:
            raise ProviderTimeoutError(
                f"ollama timed out after {self._timeout_s}s calling {path}"
            ) from exc
        except httpx.HTTPStatusError as exc:
            raise ProviderUnavailableError(
                f"ollama returned {exc.response.status_code} for {path}: {exc.response.text[:200]}"
            ) from exc
        except httpx.HTTPError as exc:
            raise ProviderUnavailableError(
                f"could not reach ollama at {url}: {type(exc).__name__}: {exc}"
            ) from exc
