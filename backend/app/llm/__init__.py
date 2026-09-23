"""The LLM layer — the only door to a language model.

Invariant #1: no module outside this package calls a model directly. `get_provider()`
resolves the configured implementation, so engines depend on the protocol and never on
Ollama, on httpx, or on a model name.
"""

from functools import lru_cache

from app.core.config import LLMProviderName, get_settings
from app.llm.echo import EchoProvider, NoFixtureError
from app.llm.errors import (
    LLMError,
    PromptNotFoundError,
    ProviderTimeoutError,
    ProviderUnavailableError,
    StructuredOutputError,
)
from app.llm.ollama import OllamaProvider
from app.llm.prompts import PromptAsset, PromptLibrary, get_prompt_library
from app.llm.provider import (
    CompletionRequest,
    CompletionResponse,
    EmbeddingResponse,
    LLMProvider,
)
from app.llm.structured import extract_json, generate_structured
from app.llm.telemetry import LLMCallRecord, TelemetryCollector, get_collector


@lru_cache
def get_provider() -> LLMProvider:
    """The configured provider.

    Selected by `LLM_PROVIDER`. `echo` serves deterministic fixtures with no network, which
    is what lets CI run the full suite without a model.
    """
    settings = get_settings()
    if settings.llm_provider is LLMProviderName.ECHO:
        return EchoProvider()
    return OllamaProvider()


def reset_provider_cache() -> None:
    """Drop the cached provider. Used by tests that vary the environment."""
    get_provider.cache_clear()


__all__ = [
    "CompletionRequest",
    "CompletionResponse",
    "EchoProvider",
    "EmbeddingResponse",
    "LLMCallRecord",
    "LLMError",
    "LLMProvider",
    "NoFixtureError",
    "OllamaProvider",
    "PromptAsset",
    "PromptLibrary",
    "PromptNotFoundError",
    "ProviderTimeoutError",
    "ProviderUnavailableError",
    "StructuredOutputError",
    "TelemetryCollector",
    "extract_json",
    "generate_structured",
    "get_collector",
    "get_prompt_library",
    "get_provider",
    "reset_provider_cache",
]
