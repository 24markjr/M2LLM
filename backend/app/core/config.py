"""Application configuration.

Single source of truth for every tunable value. Nothing in the codebase reads
`os.environ` directly — invariant #7 of the implementation plan requires loop
ceilings and model identity to be configured, not hard-coded at call sites.
"""

from __future__ import annotations

from enum import StrEnum
from functools import lru_cache
from pathlib import Path

from pydantic import Field, PostgresDsn, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# backend/app/core/config.py -> backend/app/core -> backend/app -> backend -> repo root
REPO_ROOT = Path(__file__).resolve().parents[3]
ENV_FILE = REPO_ROOT / ".env"
AGENT_DIR = REPO_ROOT / ".agent"


class LLMProviderName(StrEnum):
    OLLAMA = "ollama"
    ECHO = "echo"


class ProviderMode(StrEnum):
    LOCAL = "local"
    REMOTE = "remote"


class VerificationProviderName(StrEnum):
    BASELINE = "baseline"
    REMOTE = "remote"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=ENV_FILE,
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    # --- Application ---
    app_env: str = "local"
    log_level: str = "INFO"
    api_host: str = "0.0.0.0"  # noqa: S104 — bound inside a container/dev host by design
    api_port: int = 8000

    # --- Database ---
    database_url: PostgresDsn = PostgresDsn(
        "postgresql+asyncpg://jarvis:jarvis@localhost:5432/jarvis"
    )

    # --- LLM ---
    llm_provider: LLMProviderName = LLMProviderName.OLLAMA
    ollama_base_url: str = "http://localhost:11434"
    ollama_model: str = "qwen3:4b"
    ollama_timeout_s: float = 120.0
    llm_temperature: float = 0.0
    llm_seed: int = 42

    # --- Embeddings ---
    embedding_model: str = "nomic-embed-text"
    embedding_dim: int = 768

    # --- Agent bounds ---
    max_replan_iterations: int = Field(default=3, ge=0, le=10)
    max_task_retries: int = Field(default=2, ge=0, le=5)
    max_parallel_tasks: int = Field(default=4, ge=1, le=32)
    max_tool_calls_per_run: int = Field(default=40, ge=1)
    max_plan_tasks: int = Field(default=20, ge=2)
    run_wallclock_limit_s: float = Field(default=600.0, gt=0)

    # --- Tracing ---
    trace_to_file: bool = False

    # --- Integrations ---
    context_provider: ProviderMode = ProviderMode.LOCAL
    knowledge_provider: ProviderMode = ProviderMode.LOCAL
    verification_provider: VerificationProviderName = VerificationProviderName.BASELINE
    m2context_base_url: str = ""
    knowledge_base_url: str = ""
    verification_base_url: str = ""
    integration_timeout_s: float = 30.0

    @field_validator("log_level")
    @classmethod
    def _upper(cls, v: str) -> str:
        return v.upper()

    @property
    def agent_dir(self) -> Path:
        """`.agent/` — prompts, scenarios, fixtures, traces, evals."""
        return AGENT_DIR

    @property
    def sync_database_url(self) -> str:
        """Alembic and psycopg-based tooling need the non-async driver URL."""
        return str(self.database_url).replace("+asyncpg", "")


@lru_cache
def get_settings() -> Settings:
    return Settings()
