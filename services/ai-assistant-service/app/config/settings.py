"""AI assistant service settings.

Composes ``shared_core.config``'s aggregate settings with the fields
specific to this service: host/port, CORS, JWT verification key, the
base URLs of every platform service its tools can query, and model/
RAG configuration.

**Provider credentials are read from the environment, never stored in
the database.** ``ai_agents``/``ai_prompts`` reference a provider by
name; the key for that provider comes from
``AIIOS_AI_ASSISTANT_SERVICE_<PROVIDER>_API_KEY`` at call time. A
missing key is a real configuration error surfaced at the point of
use, not a silent fallback to an unauthenticated call.
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
    RabbitMQSettings,
    RedisSettings,
)


class AiAssistantServiceSettings(BaseSettings):
    """Fields specific to this service, not covered by any shared_core section."""

    model_config = SettingsConfigDict(
        env_prefix="AIIOS_AI_ASSISTANT_SERVICE_", env_file=".env", extra="ignore"
    )

    host: str = Field(default="0.0.0.0")
    port: int = Field(default=8017, ge=1, le=65_535)
    cors_allowed_origins: list[str] = Field(default_factory=list)
    jwt_public_key_path: str = Field(default="keys/jwt_public_key.pem")

    # Platform services this assistant's own tools can query.
    inventory_service_base_url: str = Field(default="http://localhost:8007")
    discovery_service_base_url: str = Field(default="http://localhost:8008")
    configuration_service_base_url: str = Field(default="http://localhost:8010")
    automation_service_base_url: str = Field(default="http://localhost:8011")
    workflow_runtime_service_base_url: str = Field(default="http://localhost:8013")
    validation_service_base_url: str = Field(default="http://localhost:8014")
    monitoring_service_base_url: str = Field(default="http://localhost:8015")
    alerting_service_base_url: str = Field(default="http://localhost:8016")

    # Model provider endpoints. Each defaults to that provider's own
    # documented public base URL; a self-hosted deployment (Ollama,
    # vLLM, Azure) overrides its own.
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
    default_embedding_provider: str = Field(default="local")
    default_embedding_model: str = Field(default="local-hashing")

    http_client_timeout_seconds: float = Field(default=60.0, gt=0)
    max_parallel_agents: int = Field(default=5, ge=1)
    max_tool_calls_per_turn: int = Field(default=8, ge=1)
    embedding_dimensions: int = Field(default=1536, ge=8)
    rag_top_k: int = Field(default=5, ge=1)
    chunk_size_characters: int = Field(default=1200, ge=64)
    chunk_overlap_characters: int = Field(default=200, ge=0)
    conversation_memory_turns: int = Field(default=20, ge=1)


@dataclass(frozen=True, slots=True)
class Settings:
    """Every configuration section this service actually uses."""

    application: ApplicationSettings
    database: DatabaseSettings
    redis: RedisSettings
    rabbitmq: RabbitMQSettings
    email: EmailSettings
    service: AiAssistantServiceSettings


def build_settings(*, service: AiAssistantServiceSettings | None = None) -> Settings:
    """Build a :class:`Settings`, reusing the shared aggregate's current values."""
    shared = get_shared_settings()
    return Settings(
        application=shared.application,
        database=shared.database,
        redis=shared.redis,
        rabbitmq=shared.rabbitmq,
        email=shared.email,
        service=service if service is not None else AiAssistantServiceSettings(),
    )


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """The process-wide cached settings, built once."""
    return build_settings()


__all__ = ["AiAssistantServiceSettings", "Settings", "build_settings", "get_settings"]
