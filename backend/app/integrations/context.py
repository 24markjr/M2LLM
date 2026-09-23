"""The `ContextProvider` seam.

Member 2 owns the M2Context service. Member 1 owns this contract and a working local
implementation, so the retrieval story holds whether or not the remote service arrives — and
if it does, it swaps in here without touching any engine.

Selection is by environment variable. The remote adapter has a timeout and degrades to
local, recording that it did so. Silent degradation would leave a run looking like it
searched a corpus it never reached.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from app.core.config import ProviderMode, get_settings
from app.core.logging import get_logger
from app.intelligence.context.manager import LocalContextProvider, RetrievedChunk
from app.llm.provider import LLMProvider

log = get_logger(__name__)


@runtime_checkable
class ContextProvider(Protocol):
    """Semantic retrieval over the run's accumulated context."""

    async def ingest(self, documents: dict[str, str]) -> int: ...

    async def retrieve(
        self, query: str, *, k: int = 5, scope: list[str] | None = None
    ) -> list[RetrievedChunk]: ...


def build_context_provider(llm: LLMProvider) -> ContextProvider:
    """The configured provider.

    `CONTEXT_PROVIDER=remote` will select the M2Context adapter once that service exists.
    Until then the local implementation is returned and the intent is logged, rather than
    failing a run over a service that was never deployed.
    """
    settings = get_settings()
    if settings.context_provider is ProviderMode.REMOTE:
        if not settings.m2context_base_url:
            log.warning(
                "context_provider_remote_unconfigured",
                reason="M2CONTEXT_BASE_URL is empty; using the local provider",
            )
        else:
            log.info("context_provider_remote_pending", url=settings.m2context_base_url)
    return LocalContextProvider(llm)
