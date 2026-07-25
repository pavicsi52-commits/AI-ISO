"""RBAC service settings.

Composes ``shared_core.config``'s aggregate :class:`~shared_core.config
.loader.Settings` -- every AI-IOS service should depend on that rather
than reading environment variables directly, per docs/013's own
guidance -- with the handful of fields specific to this service that no
shared_core section covers (host/port, CORS origins, JWT verification
key path).
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


class RbacServiceSettings(BaseSettings):
    """Fields specific to this service, not covered by any shared_core.config section."""

    model_config = SettingsConfigDict(
        env_prefix="AIIOS_RBAC_SERVICE_", env_file=".env", extra="ignore"
    )

    host: str = Field(default="0.0.0.0")
    port: int = Field(default=8003, ge=1, le=65_535)
    cors_allowed_origins: list[str] = Field(default_factory=list)
    jwt_public_key_path: str = Field(default="keys/jwt_public_key.pem")
    permission_cache_ttl_seconds: int = Field(default=300, ge=1)


@dataclass(frozen=True, slots=True)
class Settings:
    """Every configuration section this service actually uses."""

    application: ApplicationSettings
    database: DatabaseSettings
    redis: RedisSettings
    rabbitmq: RabbitMQSettings
    email: EmailSettings
    service: RbacServiceSettings


def build_settings(*, service: RbacServiceSettings | None = None) -> Settings:
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
        service=service if service is not None else RbacServiceSettings(),
    )


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """The process-wide cached settings, built once."""
    return build_settings()


__all__ = ["RbacServiceSettings", "Settings", "build_settings", "get_settings"]
