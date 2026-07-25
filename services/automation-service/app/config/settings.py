"""Automation service settings.

Composes ``shared_core.config``'s aggregate :class:`~shared_core.config
.loader.Settings` with the handful of fields specific to this service
that no shared_core section covers: host/port, CORS origins, JWT
verification key path, and the base URLs of every platform service
this one calls out to (Inventory, Configuration Management, Secrets
Management) -- per docs/040's own SECURITY section ("Secure credential
injection"), this service never accepts or stores raw target
credentials, only secret references it resolves through
``services/secrets-management-service`` at the point of execution, the
same "credentials are never this service's own concern" precedent
``services/discovery-service``'s own ``CredentialResolver`` established.
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


class AutomationServiceSettings(BaseSettings):
    """Fields specific to this service, not covered by any shared_core.config section."""

    model_config = SettingsConfigDict(
        env_prefix="AIIOS_AUTOMATION_SERVICE_", env_file=".env", extra="ignore"
    )

    host: str = Field(default="0.0.0.0")
    port: int = Field(default=8011, ge=1, le=65_535)
    cors_allowed_origins: list[str] = Field(default_factory=list)
    jwt_public_key_path: str = Field(default="keys/jwt_public_key.pem")
    secrets_service_base_url: str = Field(default="http://localhost:8006")
    inventory_service_base_url: str = Field(default="http://localhost:8007")
    configuration_service_base_url: str = Field(default="http://localhost:8010")
    http_client_timeout_seconds: float = Field(default=10.0, gt=0)
    default_execution_timeout_seconds: int = Field(default=3600, ge=1)
    max_parallel_targets: int = Field(default=20, ge=1)


@dataclass(frozen=True, slots=True)
class Settings:
    """Every configuration section this service actually uses."""

    application: ApplicationSettings
    database: DatabaseSettings
    redis: RedisSettings
    rabbitmq: RabbitMQSettings
    email: EmailSettings
    service: AutomationServiceSettings


def build_settings(*, service: AutomationServiceSettings | None = None) -> Settings:
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
        email=shared.email,
        service=service if service is not None else AutomationServiceSettings(),
    )


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """The process-wide cached settings, built once."""
    return build_settings()


__all__ = ["AutomationServiceSettings", "Settings", "build_settings", "get_settings"]
