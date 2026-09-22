# ADR-003 — Ollama for local inference, behind a provider abstraction

## Status

Accepted — 2026-09-23 (Phase 0)

## Context

Every intelligence component in JARVIS calls a language model: intent analysis, planning,
tool tiebreaking, reasoning, verification, synthesis. The evaluation harness (Phase 20)
runs the *entire* pipeline across 20+ scenarios, repeatedly, and compares models
(Experiment 001).

That usage pattern has specific consequences:

- **Evaluation is the dominant cost driver,** not demo usage. A metered API would make
  "run the full eval suite" a decision with a price attached, which is exactly the friction
  that kills the habit of measuring.
- **Structured output reliability is the project's largest technical risk** (risk register,
  Phase 4). Small local models are worse at strict JSON than frontier hosted models. This
  argues *for* building against the harder case: a repair loop that survives a local 8B
  model will survive anything.
- **The project must run without network access** for offline demos and on machines where
  an API key cannot be shared across a four-person team.
- **Model choice must not be hard-coded** — the spec is explicit, and Experiment 001
  depends on swapping models without touching engine code.

## Decision

Ollama as the default local inference runtime, reached exclusively through the
`LLMProvider` protocol in `app/llm/provider.py`.

```python
class LLMProvider(Protocol):
    async def complete(self, req: CompletionRequest) -> CompletionResponse: ...
    async def embed(self, texts: list[str]) -> list[list[float]]: ...
    @property
    def model_id(self) -> str: ...
```

Three implementations are planned:

| Provider | `LLM_PROVIDER` | Role |
|---|---|---|
| `OllamaProvider` | `ollama` | Default. Local, offline, free at the point of use |
| `EchoProvider` | `echo` | Deterministic fixture provider. CI runs the full suite with zero network calls |
| Future hosted provider | — | Drops in without touching any engine, if a hosted model is ever wanted |

The model and embedding model are configuration (`OLLAMA_MODEL`, `EMBEDDING_MODEL`), never
literals in code.

## Reason

- **Zero marginal cost per evaluation run** is what makes the evaluation harness something
  we actually run on every change, rather than once before the presentation.
- **Fully offline** — no API key to distribute, no network dependency during a demo.
- **Building against the harder case.** The structured-output repair loop is designed for a
  model that sometimes emits malformed JSON. That makes it a real engineering component
  instead of an artifact of a forgiving API.
- **The abstraction is the actual decision.** Invariant #1 says the LLM is a component
  inside the system, not the architecture. Ollama is the current implementation of that
  component; `EchoProvider` proves the seam is real, because the whole test suite runs on it.

## Consequences

**Accepted costs**

- Local inference is slower than a hosted frontier model, so end-to-end latency figures in
  the evaluation report reflect local hardware. Reported as such, never compared to hosted
  numbers.
- Small models need the repair loop and occasionally exhaust it. Repair counts are recorded
  as telemetry and surface as an evaluation metric, rather than being hidden.
- Contributors must install Ollama and pull a model (multi-GB download).

**Gained**

- CI needs no secrets and no GPU: `LLM_PROVIDER=echo`.
- Model comparison is an environment variable, making Experiment 001 cheap to run.
- A hosted provider can be added later without any engine change — the seam is enforced by
  `tests/unit/test_llm_isolation.py`, which fails if any module outside `app/llm/` imports
  httpx or references `OLLAMA_*`.

## Local install and model choice

Installed during Phase 0 on the primary development machine: Ollama 0.34.2 (winget,
user scope), serving on `http://localhost:11434`.

**Default model: `qwen3:4b`.** Chosen against the actual hardware — an RTX 4050 laptop with
roughly 6 GB of VRAM. At ~2.6 GB the model runs fully on the GPU, which keeps a complete
evaluation sweep cheap enough to run as a habit rather than as an event. An 8B model at Q4
would partially offload to CPU on this machine and roughly triple eval wall-clock.

This is a development default, not a finding. Phase 20's Experiment 001 compares `qwen3:4b`
against a larger model on identical scenarios, measuring plan validity, dependency
correctness, tool selection and — importantly — structured-output repair count. If the
smaller model needs repeated repair passes, that is a real cost and the default changes.

Embeddings: `nomic-embed-text` (768-dim), matching the `vector(768)` column from ADR-005.
