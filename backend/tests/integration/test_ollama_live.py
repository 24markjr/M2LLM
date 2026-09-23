"""Phase 4 acceptance against the real local model.

Marked `llm` and skipped unless a provider is actually reachable, so CI stays green with
`LLM_PROVIDER=echo` and no GPU.

These are the tests that answer the question the whole phase exists for: *can a 4B local
model be made to produce valid typed output reliably enough to build an agent on?* The
answer is only meaningful when measured against the real thing.
"""

from __future__ import annotations

import asyncio

import pytest
from pydantic import Field

from app.core.config import LLMProviderName, get_settings
from app.llm.ollama import OllamaProvider
from app.llm.provider import CompletionRequest
from app.llm.structured import generate_structured
from app.llm.telemetry import TelemetryCollector, get_collector
from app.schemas.common import JarvisModel, NonEmptyStr

pytestmark = pytest.mark.llm


def _provider_available() -> bool:
    settings = get_settings()
    if settings.llm_provider is LLMProviderName.ECHO:
        return False
    try:
        return asyncio.run(OllamaProvider().health())
    except Exception:  # noqa: BLE001 - availability probe, never fails the suite
        return False


requires_model = pytest.mark.skipif(
    not _provider_available(),
    reason="no local model reachable (set LLM_PROVIDER=ollama and pull the model)",
)


class ProjectFact(JarvisModel):
    """Small, unambiguous schema. A failure here is the model, not the task."""

    project_name: NonEmptyStr
    completion_date: NonEmptyStr
    delayed: bool


class Decomposition(JarvisModel):
    """Closer to real planner output: a list of constrained strings."""

    steps: list[str] = Field(min_length=2, max_length=6)
    reason: str = ""


@requires_model
async def test_the_model_answers_at_all() -> None:
    provider = OllamaProvider()
    response = await provider.complete(
        CompletionRequest(prompt="Reply with the single word: ready", max_tokens=256)
    )
    assert response.text.strip()
    assert response.model == get_settings().ollama_model
    assert response.latency_ms > 0


@requires_model
async def test_reasoning_deliberation_never_enters_the_response() -> None:
    """qwen3 is a reasoning model; its deliberation must not reach the system.

    With thinking enabled Ollama returns a separate `thinking` field and the token budget
    is spent before any answer is produced. The provider disables it and reads only
    `response` - the first line of defence for invariant #3, before event-bus redaction.
    """
    provider = OllamaProvider()
    response = await provider.complete(
        CompletionRequest(prompt="What is 2 + 2? Answer with the number only.", max_tokens=256)
    )

    text = response.text.lower()
    assert response.text.strip(), "an empty response means thinking ate the token budget"
    assert "<think>" not in text
    assert not hasattr(response, "thinking")


@requires_model
async def test_structured_extraction_from_a_document_snippet() -> None:
    """The core Phase 4 acceptance: a valid typed object out of a real local model."""
    provider = OllamaProvider()

    result = await generate_structured(
        provider,
        ProjectFact,
        (
            "Extract the facts from this project report excerpt.\n\n"
            "EXCERPT:\n"
            "The Helix migration was scheduled to complete on 2026-04-30. "
            "The final milestone actually closed on 2026-05-14, two weeks late.\n"
        ),
        role="intent",
    )

    assert result.project_name
    assert "2026" in result.completion_date
    assert result.delayed is True


@requires_model
async def test_constrained_list_output() -> None:
    """Planner-shaped output: the min/max bounds are where small models usually slip."""
    provider = OllamaProvider()

    result = await generate_structured(
        provider,
        Decomposition,
        (
            "Break this objective into between 2 and 6 short steps:\n"
            "Compare the timeline in a project report against the budget in a "
            "financial report and identify contradictions."
        ),
        role="planner",
    )

    assert 2 <= len(result.steps) <= 6
    assert all(step.strip() for step in result.steps)


@requires_model
async def test_repair_rate_is_measured_not_assumed() -> None:
    """Records what the configured model actually costs in repair attempts.

    Not asserted against a threshold - this is a measurement, and Experiment 001 (Phase 20)
    is where it becomes a comparison. Asserting a number here would be inventing a result.
    """
    collector: TelemetryCollector = get_collector()
    collector.clear()
    provider = OllamaProvider()

    for i in range(3):
        await generate_structured(
            provider,
            ProjectFact,
            (
                f"Extract the facts. Report {i}: The Atlas project was due "
                f"2026-0{i + 1}-15 and finished on time."
            ),
            role="intent",
        )

    assert collector.total_calls >= 3
    print(
        f"\nrepair_rate={collector.repair_rate:.2f} "
        f"calls={collector.total_calls} "
        f"mean_latency_ms={collector.total_latency_ms // max(collector.total_calls, 1)}"
    )


@requires_model
async def test_embeddings_have_the_configured_dimensions() -> None:
    """A mismatch would fail at insert time in Phase 12, far from its cause."""
    provider = OllamaProvider()
    response = await provider.embed(["the project slipped two weeks"])

    assert len(response.vectors) == 1
    assert response.dimensions == get_settings().embedding_dim


@requires_model
async def test_health_reports_the_configured_model_is_present() -> None:
    assert await OllamaProvider().health() is True


async def test_health_is_false_when_nothing_is_listening() -> None:
    """Runs without a model: a wrong port must report unhealthy, not hang or raise."""
    provider = OllamaProvider(base_url="http://127.0.0.1:1", timeout_s=2.0)
    assert await provider.health() is False
