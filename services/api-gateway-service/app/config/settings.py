"""API gateway service settings.

Composes ``shared_core.config``'s aggregate with the fields specific to
this service: host/port, CORS, JWT verification key, and the routing,
rate-limit, quota, load-balancing, circuit-breaker, and caching defaults
docs/056 asks for.

**Every gateway policy below is an operator's own configuration, not a
constant buried in code.** A rate limit, a circuit-breaker threshold, or
a health-probe interval that needs a deployment to change is a policy
this service does not actually own.
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


class GatewayServiceSettings(BaseSettings):
    """Fields specific to this service, not covered by any shared_core section."""

    model_config = SettingsConfigDict(
        env_prefix="AIIOS_GATEWAY_SERVICE_", env_file=".env", extra="ignore"
    )

    host: str = Field(default="0.0.0.0")
    port: int = Field(default=8027, ge=1, le=65_535)
    cors_allowed_origins: list[str] = Field(default_factory=list)
    jwt_public_key_path: str = Field(default="keys/jwt_public_key.pem")

    # ---- proxying ------------------------------------------------------------

    upstream_connect_timeout_seconds: float = Field(default=5.0, gt=0)
    upstream_read_timeout_seconds: float = Field(default=30.0, gt=0)
    upstream_max_connections: int = Field(default=200, ge=1, le=10_000)
    upstream_max_keepalive_connections: int = Field(default=50, ge=1, le=10_000)

    # ---- rate limiting --------------------------------------------------------

    default_rate_limit_max_requests: int = Field(default=1_000, ge=1)
    default_rate_limit_window_seconds: int = Field(default=60, ge=1, le=86_400)
    default_burst_max_requests: int = Field(default=50, ge=1)
    default_burst_window_seconds: int = Field(default=1, ge=1, le=3_600)

    # ---- quotas -----------------------------------------------------------------

    default_daily_request_quota: int = Field(default=100_000, ge=1)
    default_monthly_request_quota: int = Field(default=2_000_000, ge=1)

    # ---- circuit breaker / health --------------------------------------------

    circuit_breaker_failure_threshold: int = Field(default=5, ge=1, le=1_000)
    circuit_breaker_recovery_seconds: float = Field(default=30.0, gt=0)
    health_probe_timeout_seconds: float = Field(default=3.0, gt=0)
    health_probe_cache_seconds: int = Field(default=10, ge=1, le=3_600)

    # ---- caching ----------------------------------------------------------------

    response_cache_default_ttl_seconds: int = Field(default=30, ge=1, le=86_400)
    route_cache_ttl_seconds: int = Field(default=60, ge=1, le=86_400)

    # ---- websocket --------------------------------------------------------------

    websocket_heartbeat_seconds: int = Field(default=20, ge=1, le=3_600)

    # ---- workers ------------------------------------------------------------------

    workers_enabled: bool = Field(default=True)
    health_probe_sweep_seconds: int = Field(default=15, ge=5, le=3_600)
    statistics_rollup_seconds: int = Field(default=900, ge=60, le=86_400)
    quota_reset_sweep_seconds: int = Field(default=3_600, ge=60, le=86_400)

    max_report_rows: int = Field(default=10_000, ge=1, le=1_000_000)


@dataclass(frozen=True, slots=True)
class Settings:
    """Every configuration section this service actually uses."""

    application: ApplicationSettings
    database: DatabaseSettings
    redis: RedisSettings
    rabbitmq: RabbitMQSettings
    email: EmailSettings
    service: GatewayServiceSettings


def build_settings(*, service: GatewayServiceSettings | None = None) -> Settings:
    """Build a :class:`Settings`, reusing the shared aggregate's current values."""
    shared = get_shared_settings()
    return Settings(
        application=shared.application,
        database=shared.database,
        redis=shared.redis,
        rabbitmq=shared.rabbitmq,
        email=shared.email,
        service=service if service is not None else GatewayServiceSettings(),
    )


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """The process-wide cached settings, built once."""
    return build_settings()


__all__ = [
    "GatewayServiceSettings",
    "Settings",
    "build_settings",
    "get_settings",
]
