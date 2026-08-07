"""AI agent platform service settings.

Composes ``shared_core.config``'s aggregate settings with the fields
specific to this service: host/port, CORS, JWT verification key, the
base URLs of every platform service this service's own tool-execution
kinds and guardrail checks reach live, Neo4j (Knowledge Graph tool
kind/reasoning mode), and model-provider endpoints.

**Provider credentials are read from the environment or resolved live
from secrets-management-service, never stored in the database.**
``agents``/``agent_profiles`` reference a provider by name; the key for
that provider comes from ``AIIOS_AI_AGENT_PLATFORM_SERVICE_<PROVIDER>
_API_KEY`` or a live secret reference at call time. A missing key is a
real configuration error surfaced at the point of use, not a silent
fallback to an unauthenticated call.
"""

from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict
from shared_core.config.cache import get_settings as get_shared_settings
from shared_core.config.settings import (
    ApplicationSettings,
    DatabaseSettings,
    EmailSettings,
    Neo4jSettings,
    RabbitMQSettings,
    RedisSettings,
)


class AiAgentPlatformServiceSettings(BaseSettings):
    """Fields specific to this service, not covered by any shared_core section."""

    model_config = SettingsConfigDict(
        env_prefix="AIIOS_AI_AGENT_PLATFORM_SERVICE_", env_file=".env", extra="ignore"
    )

    host: str = Field(default="0.0.0.0")
    port: int = Field(default=8031, ge=1, le=65_535)
    cors_allowed_origins: list[str] = Field(default_factory=list)
    jwt_public_key_path: str = Field(default="keys/jwt_public_key.pem")

    # ---- platform integrations this service's own tools/guardrails reach live ---

    automation_service_base_url: str = Field(default="http://localhost:8011")
    workflow_runtime_service_base_url: str = Field(default="http://localhost:8013")
    policy_engine_service_base_url: str = Field(default="http://localhost:8025")
    secrets_service_base_url: str = Field(default="http://localhost:8009")

    # ---- model provider endpoints -------------------------------------------------
    # Each defaults to that provider's own documented public base URL; a
    # self-hosted deployment (Ollama, vLLM, Azure) overrides its own.

    openai_base_url: str = Field(default="https://api.openai.com/v1")
    openai_api_key: str = Field(default="")
    azure_openai_base_url: str = Field(default="")
    azure_openai_api_key: str = Field(default="")
    anthropic_base_url: str = Field(default="https://api.anthropic.com/v1")
    anthropic_api_key: str = Field(default="")
    gemini_base_url: str = Field(default="https://generativelanguage.googleapis.com/v1beta")
    gemini_api_key: str = Field(default="")
    ollama_base_url: str = Field(default="http://localhost:11434")
    vllm_base_url: str = Field(default="http://localhost:8000/v1")
    vllm_api_key: str = Field(default="")
    openrouter_base_url: str = Field(default="https://openrouter.ai/api/v1")
    openrouter_api_key: str = Field(default="")

    default_provider: str = Field(default="ollama")
    default_model: str = Field(default="llama3")

    http_client_timeout_seconds: float = Field(default=60.0, gt=0)

    # ---- task management ------------------------------------------------------------

    max_task_retries: int = Field(default=3, ge=0, le=20)
    default_task_timeout_seconds: float = Field(default=300.0, gt=0)
    max_parallel_tasks_per_workflow: int = Field(default=5, ge=1, le=100)

    # ---- sandbox ---------------------------------------------------------------------

    default_execution_timeout_seconds: float = Field(default=60.0, gt=0)
    default_memory_limit_mb: float = Field(default=512.0, gt=0)

    # ---- guardrails ------------------------------------------------------------------

    guardrails_enabled: bool = Field(default=True)
    max_reasoning_steps: int = Field(default=8, ge=1, le=64)

    # ---- health / reporting -----------------------------------------------------------

    health_check_timeout_seconds: float = Field(default=5.0, gt=0)
    health_failure_threshold: int = Field(default=3, ge=1, le=100)
    max_report_rows: int = Field(default=10_000, ge=1, le=1_000_000)

    # ---- workers ------------------------------------------------------------------------

    workers_enabled: bool = Field(default=True)
    task_dispatch_sweep_seconds: int = Field(default=15, ge=5, le=3_600)
    checkpoint_recovery_sweep_seconds: int = Field(default=60, ge=5, le=3_600)
    statistics_rollup_seconds: int = Field(default=900, ge=60, le=86_400)
    benchmark_sweep_seconds: int = Field(default=3_600, ge=60, le=86_400)


@dataclass(frozen=True, slots=True)
class Settings:
    """Every configuration section this service actually uses."""

    application: ApplicationSettings
    database: DatabaseSettings
    redis: RedisSettings
    rabbitmq: RabbitMQSettings
    email: EmailSettings
    neo4j: Neo4jSettings
    service: AiAgentPlatformServiceSettings


def build_settings(*, service: AiAgentPlatformServiceSettings | None = None) -> Settings:
    """Build a :class:`Settings`, reusing the shared aggregate's current values."""
    shared = get_shared_settings()
    return Settings(
        application=shared.application,
        database=shared.database,
        redis=shared.redis,
        rabbitmq=shared.rabbitmq,
        email=shared.email,
        neo4j=shared.neo4j,
        service=service if service is not None else AiAgentPlatformServiceSettings(),
    )


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """The process-wide cached settings, built once."""
    return build_settings()


__all__ = ["AiAgentPlatformServiceSettings", "Settings", "build_settings", "get_settings"]
