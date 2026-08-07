"""Integration hub service settings.

Composes ``shared_core.config``'s aggregate with the fields specific to
this service: host/port, CORS, JWT verification key, and the
credential/sync/health/worker defaults docs/058 asks for.

**Every policy below is an operator's own configuration, not a constant
buried in code.**
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


class IntegrationHubServiceSettings(BaseSettings):
    """Fields specific to this service, not covered by any shared_core section."""

    model_config = SettingsConfigDict(
        env_prefix="AIIOS_INTEGRATION_HUB_SERVICE_", env_file=".env", extra="ignore"
    )

    host: str = Field(default="0.0.0.0")
    port: int = Field(default=8029, ge=1, le=65_535)
    cors_allowed_origins: list[str] = Field(default_factory=list)
    jwt_public_key_path: str = Field(default="keys/jwt_public_key.pem")

    # ---- credentials ----------------------------------------------------------

    secret_encryption_key: str = Field(
        default="",
        description=(
            "Base64-encoded 32-byte key encrypting self-managed connector "
            "credentials (OAuth2 tokens this service's own token exchange "
            "obtains) at rest. Empty in this default-config only for local "
            "development convenience -- a real deployment must set this."
        ),
    )
    secrets_service_base_url: str = Field(default="http://localhost:8006")
    """Where a third-party connector credential *referenced* (not
    self-managed) by ``connector_credentials.secret_ref`` is resolved
    from -- the same precedent automation-service/discovery-service/
    configuration-management-service's own ``CredentialResolver``
    already establishes for exactly this shape of dependency."""
    secrets_resolve_timeout_seconds: float = Field(default=5.0, gt=0)

    oauth_token_timeout_seconds: float = Field(default=10.0, gt=0)
    oauth_refresh_margin_seconds: int = Field(default=300, ge=0, le=86_400)
    """Refresh an OAuth2 access token this many seconds before it
    actually expires, so a sync job never starts against a token that
    expires mid-run."""

    # ---- synchronization --------------------------------------------------------

    sync_connect_timeout_seconds: float = Field(default=5.0, gt=0)
    sync_read_timeout_seconds: float = Field(default=30.0, gt=0)
    sync_max_records_per_batch: int = Field(default=1_000, ge=1, le=100_000)

    # ---- health -------------------------------------------------------------------

    health_check_timeout_seconds: float = Field(default=5.0, gt=0)
    health_failure_threshold: int = Field(default=3, ge=1, le=100)

    max_report_rows: int = Field(default=10_000, ge=1, le=1_000_000)

    # ---- workers ------------------------------------------------------------------

    workers_enabled: bool = Field(default=True)
    health_probe_sweep_seconds: int = Field(default=60, ge=5, le=3_600)
    credential_expiry_sweep_seconds: int = Field(default=3_600, ge=60, le=86_400)
    flow_scheduler_sweep_seconds: int = Field(default=30, ge=5, le=3_600)
    statistics_rollup_seconds: int = Field(default=900, ge=60, le=86_400)


@dataclass(frozen=True, slots=True)
class Settings:
    """Every configuration section this service actually uses."""

    application: ApplicationSettings
    database: DatabaseSettings
    redis: RedisSettings
    rabbitmq: RabbitMQSettings
    email: EmailSettings
    service: IntegrationHubServiceSettings


def build_settings(*, service: IntegrationHubServiceSettings | None = None) -> Settings:
    """Build a :class:`Settings`, reusing the shared aggregate's current values."""
    shared = get_shared_settings()
    return Settings(
        application=shared.application,
        database=shared.database,
        redis=shared.redis,
        rabbitmq=shared.rabbitmq,
        email=shared.email,
        service=service if service is not None else IntegrationHubServiceSettings(),
    )


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """The process-wide cached settings, built once."""
    return build_settings()


__all__ = [
    "IntegrationHubServiceSettings",
    "Settings",
    "build_settings",
    "get_settings",
]
