"""Phase 0 — configuration contract.

These tests protect invariant #7: every agent loop ceiling is configured, bounded and
readable from one place. They deliberately do not touch the network or the database.
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.core.config import (
    LLMProviderName,
    ProviderMode,
    Settings,
    VerificationProviderName,
    get_settings,
)


def test_defaults_are_usable_without_an_env_file() -> None:
    s = Settings(_env_file=None)  # type: ignore[call-arg]

    assert s.llm_provider is LLMProviderName.OLLAMA
    assert s.context_provider is ProviderMode.LOCAL
    assert s.verification_provider is VerificationProviderName.BASELINE
    assert s.embedding_dim == 768


def test_every_loop_has_a_ceiling() -> None:
    """Invariant #7: no unbounded adaptive loop anywhere in the runtime."""
    s = Settings(_env_file=None)  # type: ignore[call-arg]

    ceilings = {
        "max_replan_iterations": s.max_replan_iterations,
        "max_task_retries": s.max_task_retries,
        "max_parallel_tasks": s.max_parallel_tasks,
        "max_tool_calls_per_run": s.max_tool_calls_per_run,
        "max_plan_tasks": s.max_plan_tasks,
    }
    for name, value in ceilings.items():
        assert value > 0, f"{name} must be a positive ceiling"
    assert s.run_wallclock_limit_s > 0


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("max_replan_iterations", 99),  # above the le=10 bound
        ("max_parallel_tasks", 0),  # below the ge=1 bound
        ("run_wallclock_limit_s", 0),  # must be gt=0
    ],
)
def test_out_of_range_ceilings_are_rejected(field: str, value: int) -> None:
    with pytest.raises(ValidationError):
        Settings(_env_file=None, **{field: value})  # type: ignore[call-arg]


def test_model_identity_is_configuration_not_a_literal() -> None:
    """ADR-003: the model must never be hard-coded at a call site."""
    s = Settings(_env_file=None, ollama_model="llama3.2")  # type: ignore[call-arg]
    assert s.ollama_model == "llama3.2"


def test_sync_url_strips_the_async_driver_for_alembic() -> None:
    s = Settings(_env_file=None)  # type: ignore[call-arg]
    assert "+asyncpg" not in s.sync_database_url
    assert s.sync_database_url.startswith("postgresql://")


def test_log_level_is_normalized() -> None:
    s = Settings(_env_file=None, log_level="debug")  # type: ignore[call-arg]
    assert s.log_level == "DEBUG"


def test_get_settings_is_cached() -> None:
    assert get_settings() is get_settings()


def test_agent_dir_points_at_the_repo_agent_folder() -> None:
    s = Settings(_env_file=None)  # type: ignore[call-arg]
    assert s.agent_dir.name == ".agent"
