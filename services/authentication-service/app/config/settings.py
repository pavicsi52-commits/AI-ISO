"""Authentication service settings.

Composes ``shared_core.config``'s aggregate :class:`~shared_core.config
.loader.Settings` -- every AI-IOS service should depend on that rather
than reading environment variables directly, per docs/013's own
guidance -- with the handful of fields specific to this service that no
shared_core section covers (host/port, CORS origins, JWT key file
paths).
"""

from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict
from shared_core.config.cache import get_settings as get_shared_settings
from shared_core.config.settings import (
    ApplicationSettings,
    AuthSettings,
    DatabaseSettings,
    EmailSettings,
    RabbitMQSettings,
    RedisSettings,
)


class AuthServiceSettings(BaseSettings):
    """Fields specific to this service, not covered by any shared_core.config section."""

    model_config = SettingsConfigDict(
        env_prefix="AIIOS_AUTH_SERVICE_", env_file=".env", extra="ignore"
    )

    host: str = Field(default="0.0.0.0")
    port: int = Field(default=8001, ge=1, le=65_535)
    cors_allowed_origins: list[str] = Field(default_factory=list)
    jwt_private_key_path: str = Field(default="keys/jwt_private_key.pem")
    jwt_public_key_path: str = Field(default="keys/jwt_public_key.pem")


@dataclass(frozen=True, slots=True)
class Settings:
    """Every configuration section this service actually uses."""

    application: ApplicationSettings
    database: DatabaseSettings
    redis: RedisSettings
    rabbitmq: RabbitMQSettings
    auth: AuthSettings
    email: EmailSettings
    service: AuthServiceSettings


def build_settings(*, service: AuthServiceSettings | None = None) -> Settings:
    """Build a :class:`Settings`, reusing the shared aggregate's current values.

    Exposed separately from :func:`get_settings` so tests can build an
    uncached instance (e.g. with an in-memory database DSN) without
    disturbing the process-wide cache.
    """
    shared = get_shared_settings()
    return Settings(
        application=shared.application,
        database=shared.database,
        redis=shared.redis,
        rabbitmq=shared.rabbitmq,
        auth=shared.auth,
        email=shared.email,
        service=service if service is not None else AuthServiceSettings(),
    )


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """The process-wide cached settings, built once."""
    return build_settings()


__all__ = ["AuthServiceSettings", "Settings", "build_settings", "get_settings"]
