"""Notification center service settings.

Composes ``shared_core.config``'s aggregate with the fields specific to
this service: host/port, CORS, JWT verification key, and the retry,
rate-limit, digest, and reporting defaults docs/055 asks for.

**Every delivery policy below is an organization's own configuration,
not a constant buried in code.** An operator adjusting how many times a
failed SMS retries, or how long a dead letter is kept before it is
purged, must not need a deployment to do it.
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


class NotificationServiceSettings(BaseSettings):
    """Fields specific to this service, not covered by any shared_core section."""

    model_config = SettingsConfigDict(
        env_prefix="AIIOS_NOTIFICATION_SERVICE_", env_file=".env", extra="ignore"
    )

    host: str = Field(default="0.0.0.0")
    port: int = Field(default=8026, ge=1, le=65_535)
    cors_allowed_origins: list[str] = Field(default_factory=list)
    jwt_public_key_path: str = Field(default="keys/jwt_public_key.pem")

    http_client_timeout_seconds: float = Field(default=30.0, gt=0)

    # ---- retries and dead letters -------------------------------------------

    default_max_attempts: int = Field(default=3, ge=1, le=100)
    default_base_delay_seconds: float = Field(default=5.0, gt=0)
    default_max_delay_seconds: float = Field(default=300.0, gt=0)
    """The ceiling an exponential backoff's delay is clamped to. Without
    one, a notification retried enough times would eventually wait
    longer between attempts than a recipient would still care about it."""

    dead_letter_retention_days: int = Field(default=90, ge=1, le=3_650)

    # ---- rate limiting --------------------------------------------------------

    rate_limit_max_per_user: int = Field(default=100, ge=1, le=1_000_000)
    rate_limit_max_per_organization: int = Field(default=10_000, ge=1, le=10_000_000)
    rate_limit_max_per_channel: int = Field(default=50_000, ge=1, le=10_000_000)
    rate_limit_max_global: int = Field(default=100_000, ge=1, le=10_000_000)
    rate_limit_window_seconds: int = Field(default=60, ge=1, le=86_400)

    # ---- digests ----------------------------------------------------------------

    digest_max_items: int = Field(default=50, ge=1, le=10_000)

    # ---- announcements ------------------------------------------------------------

    max_announcement_audience_size: int = Field(default=100_000, ge=1, le=10_000_000)

    # ---- reporting and workers ------------------------------------------------

    max_report_rows: int = Field(default=10_000, ge=1, le=1_000_000)
    report_retention_days: int = Field(default=365, ge=1, le=3_650)
    statistics_window_hours: int = Field(default=24, ge=1, le=168)

    workers_enabled: bool = Field(default=True)
    retry_sweep_seconds: int = Field(default=15, ge=5, le=3_600)
    digest_sweep_seconds: int = Field(default=300, ge=5, le=86_400)
    statistics_rollup_seconds: int = Field(default=900, ge=60, le=86_400)
    announcement_expiry_sweep_seconds: int = Field(default=300, ge=5, le=86_400)


@dataclass(frozen=True, slots=True)
class Settings:
    """Every configuration section this service actually uses."""

    application: ApplicationSettings
    database: DatabaseSettings
    redis: RedisSettings
    rabbitmq: RabbitMQSettings
    email: EmailSettings
    service: NotificationServiceSettings


def build_settings(*, service: NotificationServiceSettings | None = None) -> Settings:
    """Build a :class:`Settings`, reusing the shared aggregate's current values."""
    shared = get_shared_settings()
    return Settings(
        application=shared.application,
        database=shared.database,
        redis=shared.redis,
        rabbitmq=shared.rabbitmq,
        email=shared.email,
        service=service if service is not None else NotificationServiceSettings(),
    )


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """The process-wide cached settings, built once."""
    return build_settings()


__all__ = [
    "NotificationServiceSettings",
    "Settings",
    "build_settings",
    "get_settings",
]
