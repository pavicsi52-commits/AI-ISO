"""Scheduler service settings.

Composes ``shared_core.config``'s aggregate with the fields specific to
this service: host/port, CORS, JWT verification key, and the retry,
priority, maintenance, and reporting defaults docs/054 asks for.

**Every schedule this service fires is a policy decision an
organization is entitled to override.** Each default below is
configuration rather than a constant buried in code -- an operator
adjusting how long a job may sit queued before its priority escalates
must not need a deployment to do it.
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


class SchedulerServiceSettings(BaseSettings):
    """Fields specific to this service, not covered by any shared_core section."""

    model_config = SettingsConfigDict(
        env_prefix="AIIOS_SCHEDULER_SERVICE_", env_file=".env", extra="ignore"
    )

    host: str = Field(default="0.0.0.0")
    port: int = Field(default=8025, ge=1, le=65_535)
    cors_allowed_origins: list[str] = Field(default_factory=list)
    jwt_public_key_path: str = Field(default="keys/jwt_public_key.pem")

    http_client_timeout_seconds: float = Field(default=30.0, gt=0)

    # ---- retries ------------------------------------------------------------

    default_max_attempts: int = Field(default=3, ge=1, le=100)
    default_base_delay_seconds: float = Field(default=5.0, gt=0)
    default_max_delay_seconds: float = Field(default=300.0, gt=0)
    """The ceiling an exponential backoff's delay is clamped to. Without
    one, a job retried enough times would eventually wait longer between
    attempts than the outage it is retrying against is likely to last."""

    # ---- priority escalation ---------------------------------------------

    priority_escalation_after_minutes: int = Field(default=30, ge=1, le=1_440)
    """How long a job may sit queued before its priority escalates one
    band. A LOW-priority job queued behind a permanent backlog is
    starvation dressed up as a policy, not a real priority decision."""

    # ---- dependencies ---------------------------------------------------------

    max_dependency_depth: int = Field(default=50, ge=1, le=1_000)
    """The deepest a dependency chain may run before execution ordering
    refuses to keep resolving it. A chain with no ceiling is how a
    misconfigured dependency graph becomes an unbounded walk instead of
    a caught configuration error."""

    # ---- maintenance windows -----------------------------------------------

    max_maintenance_window_hours: int = Field(default=24, ge=1, le=168)

    # ---- due-schedule sweep -----------------------------------------------

    due_schedule_lookahead_seconds: int = Field(default=60, ge=1, le=3_600)
    """How far into the future the due-schedule sweep looks for jobs
    about to become due, so a job scheduled between two sweep ticks is
    still caught by the next one rather than sitting late until the
    following interval."""

    # ---- reporting and workers ------------------------------------------------

    max_report_rows: int = Field(default=10_000, ge=1, le=1_000_000)
    report_retention_days: int = Field(default=365, ge=1, le=3_650)
    execution_log_retention_days: int = Field(default=90, ge=1, le=3_650)
    statistics_window_hours: int = Field(default=24, ge=1, le=168)

    scheduler_enabled: bool = Field(default=True)
    due_schedule_sweep_seconds: int = Field(default=15, ge=5, le=3_600)
    retry_sweep_seconds: int = Field(default=30, ge=5, le=3_600)
    statistics_rollup_seconds: int = Field(default=900, ge=60, le=86_400)
    maintenance_sweep_seconds: int = Field(default=3_600, ge=60, le=86_400)


@dataclass(frozen=True, slots=True)
class Settings:
    """Every configuration section this service actually uses."""

    application: ApplicationSettings
    database: DatabaseSettings
    redis: RedisSettings
    rabbitmq: RabbitMQSettings
    email: EmailSettings
    service: SchedulerServiceSettings


def build_settings(*, service: SchedulerServiceSettings | None = None) -> Settings:
    """Build a :class:`Settings`, reusing the shared aggregate's current values."""
    shared = get_shared_settings()
    return Settings(
        application=shared.application,
        database=shared.database,
        redis=shared.redis,
        rabbitmq=shared.rabbitmq,
        email=shared.email,
        service=service if service is not None else SchedulerServiceSettings(),
    )


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """The process-wide cached settings, built once."""
    return build_settings()


__all__ = [
    "SchedulerServiceSettings",
    "Settings",
    "build_settings",
    "get_settings",
]
