"""Incident management service settings.

Composes ``shared_core.config``'s aggregate with the fields specific to
this service: host/port, CORS, JWT verification key, and the SLA and
escalation defaults docs/052 asks for.

**This service is where an outage becomes a coordinated response.**
Every default below is a policy decision an organization is entitled to
override, so each one is configuration rather than a constant buried in
code -- an operator adjusting a P1 acknowledgement window must not need
a deployment to do it.
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


class IncidentManagementServiceSettings(BaseSettings):
    """Fields specific to this service, not covered by any shared_core section."""

    model_config = SettingsConfigDict(
        env_prefix="AIIOS_INCIDENT_MANAGEMENT_SERVICE_", env_file=".env", extra="ignore"
    )

    host: str = Field(default="0.0.0.0")
    port: int = Field(default=8023, ge=1, le=65_535)
    cors_allowed_origins: list[str] = Field(default_factory=list)
    jwt_public_key_path: str = Field(default="keys/jwt_public_key.pem")

    http_client_timeout_seconds: float = Field(default=30.0, gt=0)

    # ---- correlation and fingerprinting --------------------------------

    correlation_window_minutes: int = Field(default=15, ge=1, le=1_440)
    """How long a fingerprint stays open for correlation before a new
    firing opens a fresh incident instead of joining the old one.

    Bounded because "forever" would mean an incident from a chronic,
    unrelated recurrence of the same alert never actually closes -- and
    "never" would mean every retry of a five-minute blip opens its own
    incident."""

    max_correlated_sources_per_incident: int = Field(default=500, ge=1, le=10_000)
    """Ceiling on how many upstream firings one incident absorbs.

    A genuinely platform-wide outage can generate thousands of
    individual alert firings in minutes; without a ceiling, correlating
    all of them onto one incident row turns the incident's own JSON
    columns into the next thing that falls over."""

    # ---- SLA and business hours -----------------------------------------

    default_business_hours_start: int = Field(default=9, ge=0, le=23)
    default_business_hours_end: int = Field(default=17, ge=1, le=24)
    default_business_days: list[int] = Field(default_factory=lambda: [0, 1, 2, 3, 4])
    """Monday=0 .. Sunday=6, matching :meth:`datetime.date.weekday`."""

    sla_warning_threshold_percent: int = Field(default=80, ge=1, le=99)
    """How far into an SLA window a warning fires, as a percentage of
    the target. 80% of a four-hour resolution SLA is 48 minutes of
    runway -- enough to actually do something with the warning, unlike
    one fired at 99%."""

    # ---- escalation -------------------------------------------------------

    max_escalation_levels: int = Field(default=5, ge=1, le=20)
    escalation_sweep_seconds: int = Field(default=60, ge=15, le=3_600)
    """How often the leader-elected sweep checks for SLAs about to breach
    or already breached. Short by this service's standards, deliberately
    -- an escalation discovered five minutes late is five minutes an
    incident commander was not paged."""

    # ---- major incidents --------------------------------------------------

    major_incident_status_update_minutes: int = Field(default=30, ge=1, le=1_440)
    war_room_idle_close_minutes: int = Field(default=1_440, ge=1, le=43_200)
    """How long a war room may sit with no new timeline activity before
    the maintenance sweep flags it for stand-down. A forgotten war room
    left "active" is a coordination space that looks staffed and is
    not, which is worse for the next incident than one that was
    properly closed."""

    postmortem_due_days: int = Field(default=5, ge=1, le=90)
    """How long after a major incident resolves before the maintenance
    sweep starts reminding its commander that no postmortem exists yet.
    The reminder a "blameless learning culture" actually depends on --
    see ``IncidentNotificationService.send_postmortem_due``."""

    # ---- reporting and workers ---------------------------------------------

    max_report_rows: int = Field(default=10_000, ge=1, le=1_000_000)
    report_retention_days: int = Field(default=730, ge=1, le=3_650)
    statistics_window_hours: int = Field(default=24, ge=1, le=168)

    scheduler_enabled: bool = Field(default=True)
    sla_sweep_seconds: int = Field(default=60, ge=15, le=3_600)
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
    service: IncidentManagementServiceSettings


def build_settings(*, service: IncidentManagementServiceSettings | None = None) -> Settings:
    """Build a :class:`Settings`, reusing the shared aggregate's current values."""
    shared = get_shared_settings()
    return Settings(
        application=shared.application,
        database=shared.database,
        redis=shared.redis,
        rabbitmq=shared.rabbitmq,
        email=shared.email,
        service=service if service is not None else IncidentManagementServiceSettings(),
    )


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """The process-wide cached settings, built once."""
    return build_settings()


__all__ = [
    "IncidentManagementServiceSettings",
    "Settings",
    "build_settings",
    "get_settings",
]
