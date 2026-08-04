"""Change management service settings.

Composes ``shared_core.config``'s aggregate with the fields specific to
this service: host/port, CORS, JWT verification key, and the risk,
approval, calendar, and PIR defaults docs/053 asks for.

**Every change this service tracks touches something already running.**
Every default below is a policy decision an organization is entitled to
override, so each one is configuration rather than a constant buried in
code -- an operator adjusting how many CAB approvers a high-risk change
needs must not need a deployment to do it.
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


class ChangeManagementServiceSettings(BaseSettings):
    """Fields specific to this service, not covered by any shared_core section."""

    model_config = SettingsConfigDict(
        env_prefix="AIIOS_CHANGE_MANAGEMENT_SERVICE_", env_file=".env", extra="ignore"
    )

    host: str = Field(default="0.0.0.0")
    port: int = Field(default=8024, ge=1, le=65_535)
    cors_allowed_origins: list[str] = Field(default_factory=list)
    jwt_public_key_path: str = Field(default="keys/jwt_public_key.pem")

    http_client_timeout_seconds: float = Field(default=30.0, gt=0)

    # ---- risk assessment -----------------------------------------------

    minimum_approvals_high_risk: int = Field(default=2, ge=1, le=20)
    """How many distinct approvers a high-or-critical-risk change needs
    before it may schedule. A single approver on the riskiest changes
    means one person's blind spot is the only check the platform
    provides -- the exact gap a CAB exists to close."""

    emergency_change_requires_post_hoc_approval: bool = Field(default=True)
    """An emergency change may implement before approval completes, but
    never without one existing at all -- this only controls whether that
    approval may be recorded after the fact rather than before."""

    # ---- CAB --------------------------------------------------------------

    cab_quorum_fraction: float = Field(default=0.5, gt=0.0, le=1.0)
    """The fraction of invited CAB members who must vote before a
    meeting's outcome counts. A vote of one person present is not a
    board decision, and a fixed absolute quorum would misbehave as a
    board's membership grows or shrinks."""

    # ---- change calendar ----------------------------------------------------

    default_business_hours_start: int = Field(default=9, ge=0, le=23)
    default_business_hours_end: int = Field(default=17, ge=1, le=24)
    default_business_days: list[int] = Field(default_factory=lambda: [0, 1, 2, 3, 4])
    """Monday=0 .. Sunday=6, matching :meth:`datetime.date.weekday`."""

    max_maintenance_window_hours: int = Field(default=12, ge=1, le=168)
    """The longest a single maintenance window may run. A window with no
    ceiling is how "planned change" and "extended outage" stop being
    distinguishable on a calendar."""

    # ---- conflict detection --------------------------------------------------

    conflict_detection_window_hours: int = Field(default=4, ge=1, le=168)
    """How much slack around a proposed window still counts as
    conflicting. Two changes scheduled back-to-back on the same asset
    are a real scheduling risk even when their windows never technically
    overlap -- the crew finishing the first one is the crew about to
    start the second."""

    # ---- PIR ------------------------------------------------------------------

    pir_due_days: int = Field(default=5, ge=1, le=90)
    """How long after implementation completes before the maintenance
    sweep starts reminding a change's owner that no post-implementation
    review exists yet."""

    # ---- reporting and workers ---------------------------------------------

    max_report_rows: int = Field(default=10_000, ge=1, le=1_000_000)
    report_retention_days: int = Field(default=730, ge=1, le=3_650)
    statistics_window_hours: int = Field(default=24, ge=1, le=168)

    scheduler_enabled: bool = Field(default=True)
    conflict_sweep_seconds: int = Field(default=300, ge=15, le=3_600)
    approval_expiry_sweep_seconds: int = Field(default=3_600, ge=60, le=86_400)
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
    service: ChangeManagementServiceSettings


def build_settings(*, service: ChangeManagementServiceSettings | None = None) -> Settings:
    """Build a :class:`Settings`, reusing the shared aggregate's current values."""
    shared = get_shared_settings()
    return Settings(
        application=shared.application,
        database=shared.database,
        redis=shared.redis,
        rabbitmq=shared.rabbitmq,
        email=shared.email,
        service=service if service is not None else ChangeManagementServiceSettings(),
    )


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """The process-wide cached settings, built once."""
    return build_settings()


__all__ = [
    "ChangeManagementServiceSettings",
    "Settings",
    "build_settings",
    "get_settings",
]
