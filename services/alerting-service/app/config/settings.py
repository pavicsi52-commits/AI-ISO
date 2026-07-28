"""Alerting service settings.

Composes ``shared_core.config``'s aggregate :class:`~shared_core.config
.loader.Settings` with the handful of fields specific to this service
that no shared_core section covers: host/port, CORS origins, JWT
verification key path, the base URLs of every platform service this
one consumes alert-triggering signal from (Monitoring, Validation,
Automation, Workflow Runtime, Configuration Management, Discovery,
Inventory), plus rule-evaluation concurrency and deduplication/
correlation window bounds.
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


class AlertingServiceSettings(BaseSettings):
    """Fields specific to this service, not covered by any shared_core.config section."""

    model_config = SettingsConfigDict(
        env_prefix="AIIOS_ALERTING_SERVICE_", env_file=".env", extra="ignore"
    )

    host: str = Field(default="0.0.0.0")
    port: int = Field(default=8016, ge=1, le=65_535)
    cors_allowed_origins: list[str] = Field(default_factory=list)
    jwt_public_key_path: str = Field(default="keys/jwt_public_key.pem")
    monitoring_service_base_url: str = Field(default="http://localhost:8015")
    validation_service_base_url: str = Field(default="http://localhost:8014")
    automation_service_base_url: str = Field(default="http://localhost:8011")
    workflow_runtime_service_base_url: str = Field(default="http://localhost:8013")
    configuration_service_base_url: str = Field(default="http://localhost:8010")
    discovery_service_base_url: str = Field(default="http://localhost:8008")
    inventory_service_base_url: str = Field(default="http://localhost:8007")
    http_client_timeout_seconds: float = Field(default=10.0, gt=0)
    max_parallel_rule_evaluations: int = Field(default=10, ge=1)
    default_deduplication_window_seconds: float = Field(default=300.0, gt=0)
    default_correlation_window_seconds: float = Field(default=300.0, gt=0)
    default_escalation_poll_interval_seconds: float = Field(default=60.0, gt=0)
    alert_history_retention_days: int = Field(default=180, ge=1)


@dataclass(frozen=True, slots=True)
class Settings:
    """Every configuration section this service actually uses."""

    application: ApplicationSettings
    database: DatabaseSettings
    redis: RedisSettings
    rabbitmq: RabbitMQSettings
    email: EmailSettings
    service: AlertingServiceSettings


def build_settings(*, service: AlertingServiceSettings | None = None) -> Settings:
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
        service=service if service is not None else AlertingServiceSettings(),
    )


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """The process-wide cached settings, built once."""
    return build_settings()


__all__ = ["AlertingServiceSettings", "Settings", "build_settings", "get_settings"]
