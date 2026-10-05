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


class PlanningPolicyName(StrEnum):
    """Which action-selection policy the replanning loop uses.

    `naive` exists so Phase 20's Experiment 002 can measure whether the heuristic policy
    actually reduces work without reducing coverage. A policy that cannot be switched off
    cannot be evaluated.
    """

    HEURISTIC = "heuristic"
    NAIVE = "naive"


class GraphStoreName(StrEnum):
    """Where a run's knowledge graph is kept (Phase 29, ADR-010).

    `neo4j` is the default since Docker became available; `memory` is the fallback, and the store
    a run uses when Neo4j cannot be reached. Both answer every knowledge query identically.
    """

    NEO4J = "neo4j"
    MEMORY = "memory"


class VerificationProviderName(StrEnum):
    BASELINE = "baseline"
    REMOTE = "remote"
    # Member 4's verifier, ported (Phase 26): TF-IDF relevance and a shared-identifier conflict
    # rule. Deterministic, offline, no model call.
    LEXICAL = "lexical"
    # The configured model verifier and the lexical one together. See CompositeVerifier.
    COMPOSITE = "composite"


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
    # Origins the browser UI is served from. A list rather than "*" because the API is
    # credentialed, and a wildcard with credentials is rejected by every browser anyway.
    cors_origins: list[str] = Field(
        default_factory=lambda: ["http://localhost:5173", "http://127.0.0.1:5173"]
    )

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
    # How many missions the API will run at once. A local model serves one request at a
    # time, so admitting more runs than this does not make them finish sooner - it makes
    # all of them slower and the queue invisible.
    max_concurrent_runs: int = Field(default=2, ge=1, le=32)
    # Knowledge layer (Phase 28). Each chunk is one model call, so this bounds the extraction
    # loop; claims bound the memory a run's knowledge base can take.
    max_knowledge_chunks: int = Field(default=40, ge=1, le=500)
    max_knowledge_claims: int = Field(default=2000, ge=1, le=100_000)

    # --- Tracing ---
    trace_to_file: bool = False

    # --- Integrations ---
    context_provider: ProviderMode = ProviderMode.LOCAL
    knowledge_provider: ProviderMode = ProviderMode.LOCAL
    # `composite` since Phase 34, by measurement (Experiment 004): over eleven scenarios it
    # rejected the one invented finding the baseline verifier passed, and nothing else.
    verification_provider: VerificationProviderName = VerificationProviderName.COMPOSITE
    planning_policy: PlanningPolicyName = PlanningPolicyName.HEURISTIC
    m2context_base_url: str = ""
    knowledge_base_url: str = ""
    verification_base_url: str = ""
    integration_timeout_s: float = 30.0

    # --- Knowledge graph store (Phase 29) ---
    graph_store: GraphStoreName = GraphStoreName.NEO4J
    neo4j_uri: str = "bolt://localhost:7687"
    neo4j_user: str = "neo4j"
    # The local development default, matching docker-compose, as the Postgres URL above does.
    # Real deployments set NEO4J_PASSWORD; nothing outside a developer machine should use this.
    neo4j_password: str = "jarvis-neo4j"  # noqa: S105
    neo4j_database: str = "neo4j"

    # --- Experiments (Phase 34) ---
    # Overrides `agent.yaml:knowledge.cross_source_pass` for one process, so an experiment arm is
    # an environment variable rather than an edit to a committed file. Empty: the YAML decides. The
    # value is part of the evaluation config hash either way (it is read through the policy).
    knowledge_cross_source_pass: str = ""

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
