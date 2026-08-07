"""Plugin marketplace service settings.

Composes ``shared_core.config``'s aggregate with the fields specific to
this service: host/port, CORS, JWT verification key, and the
packaging/signing/sandbox/worker defaults docs/059 asks for.

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
    MinioSettings,
    RabbitMQSettings,
    RedisSettings,
)


class PluginMarketplaceServiceSettings(BaseSettings):
    """Fields specific to this service, not covered by any shared_core section."""

    model_config = SettingsConfigDict(
        env_prefix="AIIOS_PLUGIN_MARKETPLACE_SERVICE_", env_file=".env", extra="ignore"
    )

    host: str = Field(default="0.0.0.0")
    port: int = Field(default=8030, ge=1, le=65_535)
    cors_allowed_origins: list[str] = Field(default_factory=list)
    jwt_public_key_path: str = Field(default="keys/jwt_public_key.pem")

    # ---- packaging and storage -------------------------------------------------

    package_storage_bucket: str = Field(default="plugin-packages")
    max_package_size_bytes: int = Field(default=104_857_600, ge=1_024, le=1_073_741_824)

    # ---- signing ---------------------------------------------------------------

    require_signature_for_publish: bool = Field(default=True)
    """Whether ``POST /plugins/publish`` refuses an unsigned or
    invalid-signature package. Left toggleable since a fresh
    development environment may not yet have a trusted signing key
    configured."""

    # ---- sandbox -----------------------------------------------------------------

    default_execution_timeout_seconds: float = Field(default=60.0, gt=0)
    default_memory_limit_mb: float = Field(default=256.0, gt=0)

    # ---- health -------------------------------------------------------------------

    health_check_timeout_seconds: float = Field(default=5.0, gt=0)
    health_failure_threshold: int = Field(default=3, ge=1, le=100)

    max_report_rows: int = Field(default=10_000, ge=1, le=1_000_000)

    # ---- workers ------------------------------------------------------------------

    workers_enabled: bool = Field(default=True)
    health_probe_sweep_seconds: int = Field(default=60, ge=5, le=3_600)
    marketplace_approval_sweep_seconds: int = Field(default=30, ge=5, le=3_600)
    statistics_rollup_seconds: int = Field(default=900, ge=60, le=86_400)
    review_moderation_sweep_seconds: int = Field(default=120, ge=5, le=3_600)


@dataclass(frozen=True, slots=True)
class Settings:
    """Every configuration section this service actually uses."""

    application: ApplicationSettings
    database: DatabaseSettings
    redis: RedisSettings
    rabbitmq: RabbitMQSettings
    email: EmailSettings
    minio: MinioSettings
    service: PluginMarketplaceServiceSettings


def build_settings(*, service: PluginMarketplaceServiceSettings | None = None) -> Settings:
    """Build a :class:`Settings`, reusing the shared aggregate's current values."""
    shared = get_shared_settings()
    return Settings(
        application=shared.application,
        database=shared.database,
        redis=shared.redis,
        rabbitmq=shared.rabbitmq,
        email=shared.email,
        minio=shared.minio,
        service=service if service is not None else PluginMarketplaceServiceSettings(),
    )


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """The process-wide cached settings, built once."""
    return build_settings()


__all__ = [
    "PluginMarketplaceServiceSettings",
    "Settings",
    "build_settings",
    "get_settings",
]
