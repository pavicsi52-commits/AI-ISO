"""Reporting service settings.

Composes ``shared_core.config``'s aggregate settings with the fields
specific to this service: host/port, CORS, JWT verification key, the
base URLs of every platform service it draws report data from, and the
rendering/export/archive/distribution knobs.

**Every data source is read with the caller's own bearer token**, so
this service never holds a privileged credential and can never put data
into a report that the requesting user could not have fetched
themselves. That is the same decision
``services/ai-assistant-service`` made, for the same reason: RBAC stays
enforced by the service that owns the data.
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


class ReportingServiceSettings(BaseSettings):
    """Fields specific to this service, not covered by any shared_core section."""

    model_config = SettingsConfigDict(
        env_prefix="AIIOS_REPORTING_SERVICE_", env_file=".env", extra="ignore"
    )

    host: str = Field(default="0.0.0.0")
    port: int = Field(default=8018, ge=1, le=65_535)
    cors_allowed_origins: list[str] = Field(default_factory=list)
    jwt_public_key_path: str = Field(default="keys/jwt_public_key.pem")

    # Platform data sources ("DATA SOURCES").
    inventory_service_base_url: str = Field(default="http://localhost:8007")
    discovery_service_base_url: str = Field(default="http://localhost:8008")
    configuration_service_base_url: str = Field(default="http://localhost:8010")
    automation_service_base_url: str = Field(default="http://localhost:8011")
    workflow_runtime_service_base_url: str = Field(default="http://localhost:8013")
    validation_service_base_url: str = Field(default="http://localhost:8014")
    monitoring_service_base_url: str = Field(default="http://localhost:8015")
    alerting_service_base_url: str = Field(default="http://localhost:8016")
    ai_assistant_service_base_url: str = Field(default="http://localhost:8017")
    compliance_service_base_url: str = Field(default="http://localhost:8022")
    incident_service_base_url: str = Field(default="http://localhost:8023")
    administration_service_base_url: str = Field(default="http://localhost:8009")

    http_client_timeout_seconds: float = Field(default=60.0, gt=0)

    # Rendering and export.
    max_rows_per_report: int = Field(default=50_000, ge=1)
    """Hard ceiling on rows a single report may materialise.

    A report that tries to render a million rows will exhaust memory
    and take the service down for everyone; failing one report with a
    clear message is strictly better.
    """

    max_parallel_sections: int = Field(default=4, ge=1)
    """Bound on concurrent *data source* fetches while rendering.

    Sections fetch over the network, which is safe to overlap. Nothing
    here touches the database concurrently -- an ``AsyncSession`` is
    not safe for concurrent use even for reads.
    """

    template_cache_size: int = Field(default=128, ge=0)
    company_name: str = Field(default="AI-IOS")
    default_theme: str = Field(default="slate")

    # Archive and distribution.
    archive_retention_days: int = Field(default=365, ge=1)
    share_link_ttl_seconds: int = Field(default=604_800, ge=60)
    object_storage_bucket: str = Field(default="aiios-reports")
    webhook_timeout_seconds: float = Field(default=15.0, gt=0)

    # Scheduling.
    scheduler_enabled: bool = Field(default=True)
    scheduler_poll_seconds: int = Field(default=60, ge=5)
    scheduled_run_token: str = Field(default="")
    """Bearer token unattended scheduled runs read data sources with.

    A scheduled report has no requesting user, so it runs as a service
    identity. This is a deliberate, visible seam rather than a silent
    privilege escalation: the deployment decides what that identity may
    read, and every source still enforces its own RBAC against it. An
    empty token means scheduled runs can only reach sources that permit
    anonymous reads -- which in this platform is none, so a deployment
    using schedules must configure it.
    """

    # AI reporting (Prompt 046).
    ai_reporting_enabled: bool = Field(default=True)


@dataclass(frozen=True, slots=True)
class Settings:
    """Every configuration section this service actually uses."""

    application: ApplicationSettings
    database: DatabaseSettings
    redis: RedisSettings
    rabbitmq: RabbitMQSettings
    email: EmailSettings
    minio: MinioSettings
    service: ReportingServiceSettings


def build_settings(*, service: ReportingServiceSettings | None = None) -> Settings:
    """Build a :class:`Settings`, reusing the shared aggregate's current values."""
    shared = get_shared_settings()
    return Settings(
        application=shared.application,
        database=shared.database,
        redis=shared.redis,
        rabbitmq=shared.rabbitmq,
        email=shared.email,
        minio=shared.minio,
        service=service if service is not None else ReportingServiceSettings(),
    )


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """The process-wide cached settings, built once."""
    return build_settings()


__all__ = ["ReportingServiceSettings", "Settings", "build_settings", "get_settings"]
