"""Playbook service settings.

Composes ``shared_core.config``'s aggregate :class:`~shared_core.config
.loader.Settings` with the handful of fields specific to this service
that no shared_core section covers: host/port, CORS origins, JWT
verification key path, and the signing keypair's own file paths.

Docs/041's own SECURITY section says "Integrate Prompt 032" (RBAC) --
the same instruction docs/039/docs/040's own SECURITY sections already
gave, satisfied there (and here) by authentication (``CurrentUserId``)
plus organization/project-scoped queries on every list/search/analytics
call, without a live per-request RBAC permission-check HTTP call --
neither prior service built one, and no field in this service's own
PLAYBOOK MODEL needs one. Likewise "Integrate Prompt 035" (Secrets):
unlike ``ConfigurationGitRepository.credential_ref`` in docs/039, no
field anywhere in this service's own data model stores a
secrets-management-service reference -- the signing keypair is this
service's own key material, loaded from a local file exactly like the
JWT verification key every downstream AI-IOS service already loads,
not a secret resolved from another service.
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


class PlaybookServiceSettings(BaseSettings):
    """Fields specific to this service, not covered by any shared_core.config section."""

    model_config = SettingsConfigDict(
        env_prefix="AIIOS_PLAYBOOK_SERVICE_", env_file=".env", extra="ignore"
    )

    host: str = Field(default="0.0.0.0")
    port: int = Field(default=8012, ge=1, le=65_535)
    cors_allowed_origins: list[str] = Field(default_factory=list)
    jwt_public_key_path: str = Field(default="keys/jwt_public_key.pem")
    signing_private_key_path: str = Field(default="keys/signing_private_key.pem")
    signing_public_key_path: str = Field(default="keys/signing_public_key.pem")


@dataclass(frozen=True, slots=True)
class Settings:
    """Every configuration section this service actually uses."""

    application: ApplicationSettings
    database: DatabaseSettings
    redis: RedisSettings
    rabbitmq: RabbitMQSettings
    email: EmailSettings
    service: PlaybookServiceSettings


def build_settings(*, service: PlaybookServiceSettings | None = None) -> Settings:
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
        service=service if service is not None else PlaybookServiceSettings(),
    )


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """The process-wide cached settings, built once."""
    return build_settings()


__all__ = ["PlaybookServiceSettings", "Settings", "build_settings", "get_settings"]
