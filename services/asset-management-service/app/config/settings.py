"""Asset management service settings.

Composes ``shared_core.config``'s aggregate :class:`~shared_core.config
.loader.Settings` with the handful of fields specific to this service
that no shared_core section covers: host/port, CORS origins, JWT
verification key path, and the base URL of ``inventory-service`` --
this service correlates every :class:`~app.models.managed_asset
.ManagedAsset` against an ``inventory-service`` asset via
``inventory_asset_id`` and validates that asset exists before
governing it, matching ``services/discovery-service``'s own
``inventory_service_base_url`` precedent.

Unlike ``discovery-service``, this service never calls
``secrets-management-service`` (it holds no scan credentials) and its
Neo4j usage is read-only against the graph ``inventory-service`` has
already populated (per docs/038's own framing: "Inventory identifies
assets. Asset Management manages assets."), so ``neo4j: Neo4jSettings``
is reused identically but no write-path settings are added.
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


class AssetManagementServiceSettings(BaseSettings):
    """Fields specific to this service, not covered by any shared_core.config section."""

    model_config = SettingsConfigDict(
        env_prefix="AIIOS_ASSET_MANAGEMENT_SERVICE_", env_file=".env", extra="ignore"
    )

    host: str = Field(default="0.0.0.0")
    port: int = Field(default=8009, ge=1, le=65_535)
    cors_allowed_origins: list[str] = Field(default_factory=list)
    jwt_public_key_path: str = Field(default="keys/jwt_public_key.pem")
    inventory_service_base_url: str = Field(default="http://localhost:8007")
    http_client_timeout_seconds: float = Field(default=10.0, gt=0)
    dependency_graph_max_depth: int = Field(default=5, ge=1, le=10)


@dataclass(frozen=True, slots=True)
class Settings:
    """Every configuration section this service actually uses."""

    application: ApplicationSettings
    database: DatabaseSettings
    redis: RedisSettings
    rabbitmq: RabbitMQSettings
    neo4j: Neo4jSettings
    email: EmailSettings
    service: AssetManagementServiceSettings


def build_settings(*, service: AssetManagementServiceSettings | None = None) -> Settings:
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
        neo4j=shared.neo4j,
        email=shared.email,
        service=service if service is not None else AssetManagementServiceSettings(),
    )


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """The process-wide cached settings, built once."""
    return build_settings()


__all__ = ["AssetManagementServiceSettings", "Settings", "build_settings", "get_settings"]
