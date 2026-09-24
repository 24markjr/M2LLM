"""Loader for `.agent/config/*.yaml` — agent behaviour policy.

Two configuration surfaces exist, and the split is deliberate (see `.agent/README.md`):

- `.env` -> `Settings`: **where things are, and hard safety ceilings.** Operator-owned.
- `.agent/config/*.yaml`: **how the agent behaves.** Engineer-owned, committed, reviewed.

**The rule that makes the split safe: YAML can never exceed an `.env` ceiling.** Behaviour
policy is tunable from inside the repository; safety bounds are not. `clamp()` enforces it
and logs every clamp, so a silently-ignored setting is impossible.

This module types `models.yaml` in full (consumed now, Phase 4) and the ceiling fields of
`agent.yaml`. The rest of `agent.yaml` is typed in Phase 16, `tools.yaml` in Phases 9-10 and
`evaluation.yaml` in Phase 20 — each when there is code that reads it, rather than building
configuration nothing consumes.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml
from pydantic import Field

from app.core.config import Settings, get_settings
from app.core.logging import get_logger
from app.schemas.common import JarvisModel

log = get_logger(__name__)


class AgentConfigError(RuntimeError):
    """A config file is missing or malformed. Fail loudly at startup, never at task time."""


def _config_dir() -> Path:
    return get_settings().agent_dir / "config"


def load_yaml(name: str) -> dict[str, Any]:
    path = _config_dir() / name
    if not path.exists():
        raise AgentConfigError(f"missing agent config: {path}")
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
    except yaml.YAMLError as exc:
        raise AgentConfigError(f"malformed YAML in {path}: {exc}") from exc
    if not isinstance(data, dict):
        raise AgentConfigError(f"{path} must contain a mapping at the top level")
    return data


def clamp[N: (int, float)](value: N, ceiling: N, *, name: str) -> N:
    """Hold a requested value to its hard ceiling, and say so when it bites.

    A clamp is never silent. A run that quietly ignored a configured value would be
    impossible to explain afterwards.
    """
    if value > ceiling:
        log.warning(
            "agent_config_clamped",
            setting=name,
            requested=value,
            applied=ceiling,
            reason="exceeds the ceiling in .env / Settings",
        )
        return ceiling
    return value


# --- models.yaml ---------------------------------------------------------------


class GenerationParams(JarvisModel):
    """Generation settings for one agent role."""

    model: str
    temperature: float = Field(default=0.0, ge=0.0, le=2.0)
    seed: int = 42
    top_p: float = Field(default=0.9, gt=0.0, le=1.0)
    max_tokens: int = Field(default=2048, ge=1)
    # Provider-level JSON constraint, where the provider supports one.
    format: str = "json"
    # Reasoning-model deliberation pass. Off by default - see ADR-003.
    think: bool = False


class StructuredOutputPolicy(JarvisModel):
    """How hard to try when a model emits malformed JSON.

    The largest practical risk in the project: small local models get strict JSON wrong often
    enough that the repair loop has to be a real component rather than a retry.
    """

    max_repairs: int = Field(default=2, ge=0, le=5)
    # After exhausting repairs: raise, so the caller decides to degrade or fail the task.
    # It never guesses.
    on_exhausted: str = "raise"
    record_repair_telemetry: bool = True


class EmbeddingConfig(JarvisModel):
    model: str = "nomic-embed-text"
    dimensions: int = Field(default=768, ge=1)
    batch_size: int = Field(default=32, ge=1)


class ModelsConfig(JarvisModel):
    """Parsed `models.yaml`.

    Engines ask for a *role*; this maps roles to models. No engine ever names a model
    (ADR-003).
    """

    version: int = 1
    # The YAML anchor template (`default: &default`) survives parsing as a real key, since
    # anchors are a serialization feature rather than a document one. Accepted and ignored:
    # roles carry their own fully-merged values.
    default: GenerationParams | None = None
    roles: dict[str, GenerationParams]
    embeddings: EmbeddingConfig = Field(default_factory=EmbeddingConfig)
    structured_output: StructuredOutputPolicy = Field(default_factory=StructuredOutputPolicy)
    comparison_candidates: list[str] = Field(default_factory=list)

    def params_for(self, role: str) -> GenerationParams:
        if role not in self.roles:
            raise AgentConfigError(
                f"unknown model role '{role}'; known roles: {sorted(self.roles)}"
            )
        return self.roles[role]


def _apply_settings_overrides(config: ModelsConfig, settings: Settings) -> ModelsConfig:
    """`.env` wins over YAML for identity and determinism.

    Experiment 001 swaps models with an environment variable, so `OLLAMA_MODEL` has to
    override the file rather than the other way round.
    """
    roles = {
        name: params.model_copy(
            update={
                "model": settings.ollama_model,
                "temperature": settings.llm_temperature
                if params.temperature == 0.0
                else params.temperature,
                "seed": settings.llm_seed,
            }
        )
        for name, params in config.roles.items()
    }
    embeddings = config.embeddings.model_copy(
        update={
            "model": settings.embedding_model,
            "dimensions": settings.embedding_dim,
        }
    )
    return config.model_copy(update={"roles": roles, "embeddings": embeddings})


@lru_cache
def get_models_config() -> ModelsConfig:
    raw = load_yaml("models.yaml")
    # YAML anchors are expanded by the parser, so each role arrives fully resolved.
    config = ModelsConfig.model_validate(raw)
    return _apply_settings_overrides(config, get_settings())


# --- agent.yaml (ceilings only; the rest is typed in Phase 16) -----------------


class AgentBounds(JarvisModel):
    """The ceiling fields of `agent.yaml`, after clamping against `Settings`.

    These are the values the runtime actually uses. Anything requested above its `.env`
    ceiling has already been reduced and logged by the time it appears here.
    """

    max_replan_iterations: int = Field(ge=0)
    max_parallel_tasks: int = Field(ge=1)
    max_task_retries: int = Field(ge=0)
    max_plan_tasks: int = Field(ge=2)
    max_tool_calls_per_run: int = Field(ge=1)
    wallclock_limit_s: float = Field(gt=0)
    diminishing_returns_epsilon: float = Field(ge=0.0, le=1.0)
    # Tokens of observations allowed into the reasoning prompt. An input budget, not a
    # generation limit - see agent.yaml for why the distinction is load-bearing.
    observation_budget_tokens: int = Field(default=6000, ge=500)


@lru_cache
def get_agent_bounds() -> AgentBounds:
    raw = load_yaml("agent.yaml")
    settings = get_settings()

    replanning = raw.get("replanning", {})
    execution = raw.get("execution", {})
    planning = raw.get("planning", {})
    budget = raw.get("budget", {})
    termination = replanning.get("termination", {})
    reasoning = raw.get("reasoning", {})
    retry = execution.get("retry", {})

    return AgentBounds(
        observation_budget_tokens=int(reasoning.get("observation_budget_tokens", 6000)),
        max_replan_iterations=clamp(
            int(replanning.get("max_iterations", settings.max_replan_iterations)),
            settings.max_replan_iterations,
            name="replanning.max_iterations",
        ),
        max_parallel_tasks=clamp(
            int(execution.get("max_parallel_tasks", settings.max_parallel_tasks)),
            settings.max_parallel_tasks,
            name="execution.max_parallel_tasks",
        ),
        max_task_retries=clamp(
            int(retry.get("max_attempts", settings.max_task_retries)),
            settings.max_task_retries,
            name="execution.retry.max_attempts",
        ),
        max_plan_tasks=clamp(
            int(planning.get("max_tasks", settings.max_plan_tasks)),
            settings.max_plan_tasks,
            name="planning.max_tasks",
        ),
        max_tool_calls_per_run=clamp(
            int(budget.get("max_tool_calls_per_run", settings.max_tool_calls_per_run)),
            settings.max_tool_calls_per_run,
            name="budget.max_tool_calls_per_run",
        ),
        wallclock_limit_s=clamp(
            float(budget.get("wallclock_limit_s", settings.run_wallclock_limit_s)),
            settings.run_wallclock_limit_s,
            name="budget.wallclock_limit_s",
        ),
        diminishing_returns_epsilon=float(termination.get("diminishing_returns_epsilon", 0.05)),
    )


def reset_config_cache() -> None:
    """Drop cached configs. Used by tests that vary the environment."""
    get_models_config.cache_clear()
    get_agent_bounds.cache_clear()
