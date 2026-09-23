"""Phase 4 — the two configuration surfaces, and the rule that keeps them safe.

`.env`/`Settings` holds infrastructure and hard safety ceilings. `.agent/config/*.yaml`
holds agent behaviour policy. The YAML can never exceed an `.env` ceiling, and a clamp is
never silent.
"""

from __future__ import annotations

import pytest

from app.core.agent_config import (
    AgentConfigError,
    GenerationParams,
    ModelsConfig,
    clamp,
    get_agent_bounds,
    get_models_config,
    load_yaml,
    reset_config_cache,
)
from app.core.config import get_settings


@pytest.fixture(autouse=True)
def _clear_cache() -> None:
    reset_config_cache()


# --- the clamping rule ---------------------------------------------------------


def test_a_value_within_its_ceiling_passes_through() -> None:
    assert clamp(3, 5, name="x") == 3


def test_a_value_above_its_ceiling_is_reduced() -> None:
    """Behaviour policy is tunable from the repo; safety bounds are not."""
    assert clamp(8, 3, name="replanning.max_iterations") == 3


def test_clamping_works_for_floats_too() -> None:
    assert clamp(900.0, 600.0, name="budget.wallclock_limit_s") == 600.0


def test_no_configured_bound_can_exceed_its_settings_ceiling() -> None:
    """The invariant, checked against the real config files."""
    bounds = get_agent_bounds()
    settings = get_settings()

    assert bounds.max_replan_iterations <= settings.max_replan_iterations
    assert bounds.max_parallel_tasks <= settings.max_parallel_tasks
    assert bounds.max_task_retries <= settings.max_task_retries
    assert bounds.max_plan_tasks <= settings.max_plan_tasks
    assert bounds.max_tool_calls_per_run <= settings.max_tool_calls_per_run
    assert bounds.wallclock_limit_s <= settings.run_wallclock_limit_s


def test_every_bound_is_positive() -> None:
    """Invariant #7 again, now against the loaded policy rather than the defaults."""
    bounds = get_agent_bounds()
    assert bounds.max_replan_iterations >= 0
    assert bounds.max_parallel_tasks >= 1
    assert bounds.max_plan_tasks >= 2
    assert bounds.max_tool_calls_per_run >= 1
    assert bounds.wallclock_limit_s > 0


def test_diminishing_returns_epsilon_is_loaded() -> None:
    """The stop condition that distinguishes 'recognised it was not worth another
    iteration' from 'burned the whole budget'."""
    assert 0.0 <= get_agent_bounds().diminishing_returns_epsilon <= 1.0


# --- models.yaml ---------------------------------------------------------------


def test_every_agent_role_has_a_model_assignment() -> None:
    """An engine asking for a role that does not exist is a startup failure, not a
    task-time surprise."""
    config = get_models_config()
    expected = {
        "intent",
        "planner",
        "router",
        "reasoning",
        "verification",
        "synthesis",
        "evidence_gap",
    }
    assert expected <= set(config.roles)


def test_env_overrides_the_yaml_model(monkeypatch: pytest.MonkeyPatch) -> None:
    """Experiment 001 swaps models with an environment variable, so .env must win."""
    config = get_models_config()
    settings = get_settings()
    for params in config.roles.values():
        assert params.model == settings.ollama_model


def test_embedding_dimensions_match_the_vector_column() -> None:
    """A mismatch here would fail at insert time in Phase 12, far from its cause."""
    config = get_models_config()
    assert config.embeddings.dimensions == get_settings().embedding_dim


def test_asking_for_an_unknown_role_fails_with_the_known_roles_listed() -> None:
    config = get_models_config()
    with pytest.raises(AgentConfigError, match="known roles"):
        config.params_for("nonexistent_role")


def test_synthesis_is_the_only_role_allowed_any_creativity() -> None:
    """Planning and extraction are not creative tasks; reproducible plans depend on it."""
    config = get_models_config()
    for name, params in config.roles.items():
        if name == "synthesis":
            continue
        assert params.temperature == 0.0, f"role '{name}' should be deterministic"


def test_structured_output_policy_never_guesses() -> None:
    """After exhausting repairs the layer raises so the caller decides."""
    assert get_models_config().structured_output.on_exhausted == "raise"


def test_repair_telemetry_is_recorded() -> None:
    assert get_models_config().structured_output.record_repair_telemetry is True


def test_yaml_anchor_key_is_tolerated() -> None:
    """`default: &default` survives parsing as a real key. Accepted and ignored."""
    raw = load_yaml("models.yaml")
    assert "default" in raw
    assert ModelsConfig.model_validate(raw)


def test_generation_params_reject_out_of_range_values() -> None:
    from pydantic import ValidationError

    with pytest.raises(ValidationError):
        GenerationParams(model="m", temperature=5.0)
    with pytest.raises(ValidationError):
        GenerationParams(model="m", max_tokens=0)


def test_a_missing_config_file_fails_loudly() -> None:
    with pytest.raises(AgentConfigError, match="missing agent config"):
        load_yaml("does_not_exist.yaml")


def test_all_four_config_files_parse() -> None:
    for name in ("agent.yaml", "models.yaml", "tools.yaml", "evaluation.yaml"):
        assert load_yaml(name)
