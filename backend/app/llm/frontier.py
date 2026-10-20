"""Frontier (cloud) models, for the benchmark only (Phase B1).

The one place JARVIS can call a cloud model, and only from `app/evaluation/benchmark.py` on the
synthetic benchmark fixtures, when a key is configured. Investigations never come here: they run on
the local provider. Kept in `app/llm/` because only this package talks to models over HTTP.
"""

from __future__ import annotations

import time

import httpx


class FrontierError(RuntimeError):
    """A cloud model could not be reached or answered with an error."""


async def openai_chat(prompt: str, model: str, key: str, base_url: str) -> tuple[str, int]:
    """(text, latency ms) from an OpenAI-compatible chat completions endpoint, JSON mode."""
    started = time.perf_counter()
    try:
        async with httpx.AsyncClient(timeout=180) as client:
            r = await client.post(
                f"{base_url}/chat/completions",
                headers={"Authorization": f"Bearer {key}"},
                json={
                    "model": model,
                    "temperature": 0,
                    "response_format": {"type": "json_object"},
                    "messages": [{"role": "user", "content": prompt}],
                },
            )
            r.raise_for_status()
    except httpx.HTTPError as exc:
        raise FrontierError(f"{model}: {type(exc).__name__}") from exc
    return str(r.json()["choices"][0]["message"]["content"]), int(
        (time.perf_counter() - started) * 1000
    )


async def anthropic_messages(prompt: str, model: str, key: str) -> tuple[str, int]:
    """(text, latency ms) from the Anthropic Messages API."""
    started = time.perf_counter()
    try:
        async with httpx.AsyncClient(timeout=180) as client:
            r = await client.post(
                "https://api.anthropic.com/v1/messages",
                headers={"x-api-key": key, "anthropic-version": "2023-06-01"},
                json={
                    "model": model,
                    "max_tokens": 1200,
                    "temperature": 0,
                    "messages": [{"role": "user", "content": prompt}],
                },
            )
            r.raise_for_status()
    except httpx.HTTPError as exc:
        raise FrontierError(f"{model}: {type(exc).__name__}") from exc
    text = "".join(block.get("text", "") for block in r.json()["content"])
    return text, int((time.perf_counter() - started) * 1000)
