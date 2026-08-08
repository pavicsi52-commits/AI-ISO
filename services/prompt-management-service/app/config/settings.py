"""Prompt management service settings.

Composes ``shared_core.config``'s aggregate settings with the fields
specific to this service: host/port, CORS, JWT verification key, the
base URLs of the platform services this service reaches live (secrets
for ``SECRET_REFERENCE`` variables, notification center for governance
alerts, policy engine for compliance validation), rendering limits, and
the security-scanning and governance thresholds.

**No model provider credentials live here.** This service stores,
renders, evaluates, and governs prompts; it does not call models
itself. A prompt's own execution is recorded here after the fact by
whichever service ran it (ai-assistant-service, ai-agent-platform
-service), which owns its own provider credentials.
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


class PromptManagementServiceSettings(BaseSettings):
    """Fields specific to this service, not covered by any shared_core section."""

    model_config = SettingsConfigDict(
        env_prefix="AIIOS_PROMPT_MANAGEMENT_SERVICE_", env_file=".env", extra="ignore"
    )

    host: str = Field(default="0.0.0.0")
    port: int = Field(default=8032, ge=1, le=65_535)
    cors_allowed_origins: list[str] = Field(default_factory=list)
    jwt_public_key_path: str = Field(default="keys/jwt_public_key.pem")

    # ---- platform integrations this service reaches live -------------------

    secrets_service_base_url: str = Field(default="http://localhost:8009")
    notification_center_base_url: str = Field(default="http://localhost:8025")
    policy_engine_service_base_url: str = Field(default="http://localhost:8025")

    http_client_timeout_seconds: float = Field(default=30.0, gt=0)

    # ---- rendering ---------------------------------------------------------

    max_rendered_length: int = Field(default=200_000, ge=1)
    """A rendered prompt longer than this is refused. A template with a
    runaway loop can otherwise produce a body large enough to exhaust
    memory before it ever reaches a model."""
    max_template_depth: int = Field(default=10, ge=1, le=64)
    """How deep template inheritance/composition may nest before the
    render is refused -- the cheap guard against a cyclic
    ``{% include %}`` chain."""
    render_timeout_seconds: float = Field(default=5.0, gt=0)

    # ---- security scanning -------------------------------------------------

    security_scanning_enabled: bool = Field(default=True)
    block_publish_on_critical: bool = Field(default=True)
    """A ``CRITICAL`` finding blocks publication outright. Configurable
    because an air-gapped deployment with its own external review gate
    may legitimately want the scan advisory instead -- but it defaults
    to blocking."""
    restricted_keywords: list[str] = Field(default_factory=list)

    # ---- governance --------------------------------------------------------

    required_approvals: int = Field(default=1, ge=1, le=10)
    approval_expiry_seconds: float = Field(default=604_800.0, gt=0)
    review_cycle_days: int = Field(default=180, ge=1, le=3_650)
    """How long a published prompt may go unreviewed before the review
    sweep flags it ("GOVERNANCE": Review Cycle)."""

    # ---- A/B testing -------------------------------------------------------

    ab_minimum_samples_per_arm: int = Field(default=100, ge=2)
    ab_significance_level: float = Field(default=0.05, gt=0, lt=1)
    ab_auto_promote: bool = Field(default=False)
    """Automatic promotion is **off** by default: promoting a winner
    publishes a new prompt version, which is exactly the action this
    service's own approval workflow exists to gate."""

    # ---- optimization ------------------------------------------------------

    optimization_enabled: bool = Field(default=True)
    compression_min_saving_ratio: float = Field(default=0.05, gt=0, lt=1)
    """A compression suggestion below this saving is not worth showing;
    churning an approved prompt's wording for a 1% token saving costs
    more in review time than it saves."""

    # ---- reporting ---------------------------------------------------------

    max_report_rows: int = Field(default=10_000, ge=1, le=1_000_000)

    # ---- workers -----------------------------------------------------------

    workers_enabled: bool = Field(default=True)
    approval_expiry_sweep_seconds: int = Field(default=300, ge=5, le=3_600)
    review_cycle_sweep_seconds: int = Field(default=3_600, ge=60, le=86_400)
    ab_test_evaluation_seconds: int = Field(default=600, ge=30, le=86_400)
    statistics_rollup_seconds: int = Field(default=900, ge=60, le=86_400)


@dataclass(frozen=True, slots=True)
class Settings:
    """Every configuration section this service actually uses."""

    application: ApplicationSettings
    database: DatabaseSettings
    redis: RedisSettings
    rabbitmq: RabbitMQSettings
    email: EmailSettings
    service: PromptManagementServiceSettings


def build_settings(*, service: PromptManagementServiceSettings | None = None) -> Settings:
    """Build a :class:`Settings`, reusing the shared aggregate's current values."""
    shared = get_shared_settings()
    return Settings(
        application=shared.application,
        database=shared.database,
        redis=shared.redis,
        rabbitmq=shared.rabbitmq,
        email=shared.email,
        service=service if service is not None else PromptManagementServiceSettings(),
    )


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """The process-wide cached settings, built once."""
    return build_settings()


__all__ = ["PromptManagementServiceSettings", "Settings", "build_settings", "get_settings"]
