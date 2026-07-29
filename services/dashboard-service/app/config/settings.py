"""Dashboard service settings.

Composes ``shared_core.config``'s aggregate settings with the fields
specific to this service: host/port, CORS, JWT verification key, the
base URLs of every platform service it draws widget data from, plus
the widget-cache, real-time, and topology knobs.

**Every data source is read with the caller's own bearer token**, so
this service never holds a privileged credential and can never put data
on a dashboard that the viewing user could not have fetched
themselves. That is the same decision ``services/reporting-service``
and ``services/ai-assistant-service`` made, for the same reason: RBAC
stays enforced by the service that owns the data.
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
    Neo4jSettings,
    RabbitMQSettings,
    RedisSettings,
)


class DashboardServiceSettings(BaseSettings):
    """Fields specific to this service, not covered by any shared_core section."""

    model_config = SettingsConfigDict(
        env_prefix="AIIOS_DASHBOARD_SERVICE_", env_file=".env", extra="ignore"
    )

    host: str = Field(default="0.0.0.0")
    port: int = Field(default=8019, ge=1, le=65_535)
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
    compliance_service_base_url: str = Field(default="http://localhost:8020")
    incident_service_base_url: str = Field(default="http://localhost:8021")
    administration_service_base_url: str = Field(default="http://localhost:8009")

    http_client_timeout_seconds: float = Field(default=60.0, gt=0)

    reporting_service_base_url: str = Field(default="http://localhost:8018")

    # Widgets and rendering.
    max_rows_per_widget: int = Field(default=5_000, ge=1)
    """Hard ceiling on rows one widget may materialise.

    A table widget that pulls a million rows will stall the dashboard
    for everyone on it; failing one widget with a clear message is
    strictly better, and the widget reports itself as failed rather
    than the whole dashboard dying.
    """

    max_parallel_widgets: int = Field(default=6, ge=1)
    """Bound on concurrent widget *data-source* fetches.

    Widgets fetch over the network, which is safe to overlap. Nothing
    here touches the database concurrently -- an ``AsyncSession`` is
    not safe for concurrent use even for reads.
    """

    widget_cache_seconds: int = Field(default=30, ge=0)
    """Default cache lifetime; a widget may set its own."""

    max_widgets_per_dashboard: int = Field(default=60, ge=1)

    # Real-time.
    realtime_enabled: bool = Field(default=True)
    stream_heartbeat_seconds: int = Field(default=20, ge=5)
    """Heartbeat cadence.

    Without one, an idle WebSocket is indistinguishable from a dead one
    and intermediate proxies close it silently -- which is exactly the
    "Connection Lost" case this service is supposed to detect.
    """

    stream_max_subscribers: int = Field(default=500, ge=1)
    presence_ttl_seconds: int = Field(default=60, ge=10)

    refresh_worker_enabled: bool = Field(default=True)
    refresh_poll_seconds: int = Field(default=15, ge=5, le=3_600)
    """How often the per-replica refresh loop re-resolves watched dashboards.

    Deliberately **not** a leader-elected scheduler job: subscribers are
    per-process, so electing one replica to do the refreshing would
    leave every other replica's watchers frozen. See
    :mod:`app.workers.refresh`.
    """

    # Analytics rollup (leader-elected -- see app/workers/registrar.py).
    scheduler_enabled: bool = Field(default=True)
    statistics_rollup_seconds: int = Field(default=900, ge=60, le=86_400)
    analytics_window_days: int = Field(default=30, ge=1, le=365)

    # Topology (Prompt 036).
    topology_enabled: bool = Field(default=True)
    topology_max_depth: int = Field(default=4, ge=1, le=10)
    """Traversal depth ceiling.

    Graph traversals grow exponentially; an unbounded blast-radius
    query on a large estate is an outage, not a visualisation.
    """

    topology_max_nodes: int = Field(default=500, ge=1)

    # Sharing and themes.
    share_link_ttl_seconds: int = Field(default=604_800, ge=60)
    default_theme_slug: str = Field(default="light")
    company_name: str = Field(default="AI-IOS")

    # AI insights (Prompt 046).
    ai_insights_enabled: bool = Field(default=True)


@dataclass(frozen=True, slots=True)
class Settings:
    """Every configuration section this service actually uses."""

    application: ApplicationSettings
    database: DatabaseSettings
    redis: RedisSettings
    rabbitmq: RabbitMQSettings
    email: EmailSettings
    neo4j: Neo4jSettings
    service: DashboardServiceSettings


def build_settings(*, service: DashboardServiceSettings | None = None) -> Settings:
    """Build a :class:`Settings`, reusing the shared aggregate's current values."""
    shared = get_shared_settings()
    return Settings(
        application=shared.application,
        database=shared.database,
        redis=shared.redis,
        rabbitmq=shared.rabbitmq,
        email=shared.email,
        neo4j=shared.neo4j,
        service=service if service is not None else DashboardServiceSettings(),
    )


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """The process-wide cached settings, built once."""
    return build_settings()


__all__ = ["DashboardServiceSettings", "Settings", "build_settings", "get_settings"]
