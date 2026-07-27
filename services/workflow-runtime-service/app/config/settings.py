"""Workflow runtime service settings.

Composes ``shared_core.config``'s aggregate :class:`~shared_core.config
.loader.Settings` with the handful of fields specific to this service
that no shared_core section covers: host/port, CORS origins, JWT
verification key path, the base URLs of every platform service this
one dispatches ``TASK``/``CONNECTOR`` nodes to (Automation), resolves
``SUB_WORKFLOW``-adjacent playbook templates through (Playbook), and
resolves dynamic targets through (Inventory), plus the approval-wait
poll interval and default execution/loop bounds. Per docs/042's own
SECURITY section ("Secure secret injection"), this service never
stores raw credentials itself -- ``VariableScope.SECRET`` values pass
through :class:`~shared_core.workflow.context.WorkflowContext` to
whichever downstream service (chiefly Automation) actually resolves
them at dispatch time, the same "credentials are never this service's
own concern" precedent ``services/automation-service``'s own
``CredentialResolver`` established.
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


class WorkflowRuntimeServiceSettings(BaseSettings):
    """Fields specific to this service, not covered by any shared_core.config section."""

    model_config = SettingsConfigDict(
        env_prefix="AIIOS_WORKFLOW_RUNTIME_SERVICE_", env_file=".env", extra="ignore"
    )

    host: str = Field(default="0.0.0.0")
    port: int = Field(default=8013, ge=1, le=65_535)
    cors_allowed_origins: list[str] = Field(default_factory=list)
    jwt_public_key_path: str = Field(default="keys/jwt_public_key.pem")
    automation_service_base_url: str = Field(default="http://localhost:8011")
    playbook_service_base_url: str = Field(default="http://localhost:8012")
    inventory_service_base_url: str = Field(default="http://localhost:8007")
    http_client_timeout_seconds: float = Field(default=10.0, gt=0)
    default_workflow_timeout_seconds: int = Field(default=3600, ge=1)
    approval_poll_interval_seconds: float = Field(default=2.0, gt=0)
    max_loop_iterations: int = Field(default=1000, ge=1)


@dataclass(frozen=True, slots=True)
class Settings:
    """Every configuration section this service actually uses."""

    application: ApplicationSettings
    database: DatabaseSettings
    redis: RedisSettings
    rabbitmq: RabbitMQSettings
    email: EmailSettings
    service: WorkflowRuntimeServiceSettings


def build_settings(*, service: WorkflowRuntimeServiceSettings | None = None) -> Settings:
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
        service=service if service is not None else WorkflowRuntimeServiceSettings(),
    )


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """The process-wide cached settings, built once."""
    return build_settings()


__all__ = ["Settings", "WorkflowRuntimeServiceSettings", "build_settings", "get_settings"]
