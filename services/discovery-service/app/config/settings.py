"""Discovery service settings.

Composes ``shared_core.config``'s aggregate :class:`~shared_core.config
.loader.Settings` -- every AI-IOS service should depend on that rather
than reading environment variables directly, per docs/013's own
guidance -- with the handful of fields specific to this service that no
shared_core section covers: host/port, CORS origins, JWT verification
key path, and the base URLs of the two other AI-IOS services this one
calls directly over HTTP (``services/secrets-management-service`` to
resolve credentials at scan time, per docs/037's own "SECURITY":
"Credentials must be retrieved only from the Secrets Management
Service"; ``services/inventory-service`` to synchronize discovered
assets and relationships, per docs/037's own "INVENTORY
SYNCHRONIZATION": "Integrate with Prompt 036"). This is the first
AI-IOS service that calls another AI-IOS service's REST API directly
rather than only sharing infrastructure with it.

Neo4j connection settings come from the shared aggregate's own
``neo4j: Neo4jSettings`` section, reused identically to
``services/inventory-service``'s own settings module.
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


class DiscoveryServiceSettings(BaseSettings):
    """Fields specific to this service, not covered by any shared_core.config section."""

    model_config = SettingsConfigDict(
        env_prefix="AIIOS_DISCOVERY_SERVICE_", env_file=".env", extra="ignore"
    )

    host: str = Field(default="0.0.0.0")
    port: int = Field(default=8008, ge=1, le=65_535)
    cors_allowed_origins: list[str] = Field(default_factory=list)
    jwt_public_key_path: str = Field(default="keys/jwt_public_key.pem")
    secrets_service_base_url: str = Field(default="http://localhost:8006")
    inventory_service_base_url: str = Field(default="http://localhost:8007")
    default_scan_timeout_seconds: int = Field(default=30, ge=1)
    default_concurrency_limit: int = Field(default=10, ge=1)
    http_client_timeout_seconds: float = Field(default=10.0, gt=0)


@dataclass(frozen=True, slots=True)
class Settings:
    """Every configuration section this service actually uses."""

    application: ApplicationSettings
    database: DatabaseSettings
    redis: RedisSettings
    rabbitmq: RabbitMQSettings
    neo4j: Neo4jSettings
    email: EmailSettings
    service: DiscoveryServiceSettings


def build_settings(*, service: DiscoveryServiceSettings | None = None) -> Settings:
    """Build a :class:`Settings`, reusing the shared aggregate's current values.

    Exposed separately from :func:`get_settings` so tests can build an
    uncached instance without disturbing the process-wide cache.
    """
    shared = get_shared_settings()
    return Settings(
        application=shared.application,
        database=shared.database,
        redis=shared.redis,
        rabbitmq=shared.rabbitmq,
        neo4j=shared.neo4j,
        email=shared.email,
        service=service if service is not None else DiscoveryServiceSettings(),
    )


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """The process-wide cached settings, built once."""
    return build_settings()


__all__ = ["DiscoveryServiceSettings", "Settings", "build_settings", "get_settings"]
