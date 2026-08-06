"""Webhook service settings.

Composes ``shared_core.config``'s aggregate with the fields specific to
this service: host/port, CORS, JWT verification key, and the
delivery/retry/idempotency/security defaults docs/057 asks for.

**Every policy below is an operator's own configuration, not a constant
buried in code.** A retry limit, a signature TTL, or a sweep interval
that needs a deployment to change is a policy this service does not
actually own.
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


class WebhookServiceSettings(BaseSettings):
    """Fields specific to this service, not covered by any shared_core section."""

    model_config = SettingsConfigDict(
        env_prefix="AIIOS_WEBHOOK_SERVICE_", env_file=".env", extra="ignore"
    )

    host: str = Field(default="0.0.0.0")
    port: int = Field(default=8028, ge=1, le=65_535)
    cors_allowed_origins: list[str] = Field(default_factory=list)
    jwt_public_key_path: str = Field(default="keys/jwt_public_key.pem")

    # ---- signing secrets ----------------------------------------------------

    secret_encryption_key: str = Field(
        default="",
        description=(
            "Base64-encoded 32-byte key encrypting webhook signing secrets at "
            "rest. Empty in this default-config only for local development "
            "convenience -- a real deployment must set this."
        ),
    )
    default_signature_algorithm: str = Field(default="hmac_sha256")
    signature_timestamp_tolerance_seconds: int = Field(default=300, ge=1, le=86_400)

    # ---- delivery ----------------------------------------------------------

    delivery_connect_timeout_seconds: float = Field(default=5.0, gt=0)
    delivery_read_timeout_seconds: float = Field(default=15.0, gt=0)
    delivery_max_connections: int = Field(default=200, ge=1, le=10_000)
    delivery_max_keepalive_connections: int = Field(default=50, ge=1, le=10_000)
    max_payload_bytes: int = Field(default=1_048_576, ge=1_024, le=104_857_600)

    # ---- retry ---------------------------------------------------------------

    default_max_attempts: int = Field(default=8, ge=1, le=50)
    default_base_delay_seconds: float = Field(default=5.0, gt=0)
    default_max_delay_seconds: float = Field(default=3_600.0, gt=0)

    # ---- idempotency ----------------------------------------------------------

    idempotency_key_ttl_seconds: int = Field(default=86_400, ge=60, le=2_592_000)

    # ---- workers ------------------------------------------------------------------

    workers_enabled: bool = Field(default=True)
    retry_sweep_seconds: int = Field(default=15, ge=5, le=3_600)
    replay_processor_sweep_seconds: int = Field(default=10, ge=5, le=3_600)
    statistics_rollup_seconds: int = Field(default=900, ge=60, le=86_400)
    idempotency_expiry_sweep_seconds: int = Field(default=3_600, ge=60, le=86_400)

    max_report_rows: int = Field(default=10_000, ge=1, le=1_000_000)


@dataclass(frozen=True, slots=True)
class Settings:
    """Every configuration section this service actually uses."""

    application: ApplicationSettings
    database: DatabaseSettings
    redis: RedisSettings
    rabbitmq: RabbitMQSettings
    email: EmailSettings
    service: WebhookServiceSettings


def build_settings(*, service: WebhookServiceSettings | None = None) -> Settings:
    """Build a :class:`Settings`, reusing the shared aggregate's current values."""
    shared = get_shared_settings()
    return Settings(
        application=shared.application,
        database=shared.database,
        redis=shared.redis,
        rabbitmq=shared.rabbitmq,
        email=shared.email,
        service=service if service is not None else WebhookServiceSettings(),
    )


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """The process-wide cached settings, built once."""
    return build_settings()


__all__ = [
    "Settings",
    "WebhookServiceSettings",
    "build_settings",
    "get_settings",
]
