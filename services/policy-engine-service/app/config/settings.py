"""Policy engine service settings.

Composes ``shared_core.config``'s aggregate with the fields specific to
this service: host/port, CORS, JWT verification key, and the knobs that
bound policy evaluation.

**Evaluation is on the critical path of every protected operation on the
platform.** Every other service calls here before doing anything that
matters, so the ceilings below are not tuning preferences -- they are
what stops one badly-authored policy from becoming a platform-wide
outage. They live in configuration so an operator can lower them without
a deployment; none can be raised past the hard limits the rule engine
itself enforces.
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


class PolicyEngineServiceSettings(BaseSettings):
    """Fields specific to this service, not covered by any shared_core section."""

    model_config = SettingsConfigDict(
        env_prefix="AIIOS_POLICY_ENGINE_SERVICE_", env_file=".env", extra="ignore"
    )

    host: str = Field(default="0.0.0.0")
    port: int = Field(default=8021, ge=1, le=65_535)
    cors_allowed_origins: list[str] = Field(default_factory=list)
    jwt_public_key_path: str = Field(default="keys/jwt_public_key.pem")

    http_client_timeout_seconds: float = Field(default=30.0, gt=0)

    # ---- evaluation ceilings ------------------------------------------

    max_policies_per_evaluation: int = Field(default=500, ge=1, le=5_000)
    """How many policies one decision may consider.

    A decision that loads the whole catalogue on every call is a
    decision whose latency grows with how much governance an
    organization has written -- which punishes exactly the customers who
    use the product properly. Candidate selection narrows by category,
    resource, and action first; this bounds what is left.
    """

    max_evaluation_milliseconds: int = Field(default=2_000, ge=10, le=60_000)
    """Soft budget for one evaluation, reported rather than enforced.

    Not a timeout: cancelling an authorization decision halfway leaves
    the caller with no answer, which is worse than a slow one. Exceeding
    it marks the decision slow and emits a warning, so a pathological
    policy is visible before it is load-bearing.
    """

    default_effect_on_no_match: str = Field(default="deny")
    """What to answer when no policy matches at all.

    Deny by default. An engine that allows what it has no opinion about
    is an engine that grants everything until somebody remembers to
    write a policy, and the gap between deploying this service and
    authoring the first policy is precisely when that matters.
    """

    fail_closed: bool = Field(default=True)
    """Whether an evaluation error denies rather than allows.

    Closed by default, and this is the setting most worth understanding
    before changing. Open would mean a database blip, a malformed stored
    policy, or an unreachable attribute silently authorizes whatever was
    asked. The cost of closed is a real outage during an incident; the
    cost of open is an invisible one, and only the first gets noticed.
    """

    # ---- decision caching ---------------------------------------------

    decision_cache_enabled: bool = Field(default=True)
    decision_cache_ttl_seconds: int = Field(default=30, ge=1, le=3_600)
    """How long a decision may be reused.

    Short on purpose. A cached authorization is a decision made against
    a policy catalogue that may since have changed, and the window
    between publishing a deny and it taking effect is a window in which
    the estate is governed by yesterday's rules. Publishing invalidates
    the cache explicitly; this TTL is the backstop for everything
    invalidation might miss.
    """

    cache_only_permitting_decisions: bool = Field(default=False)
    """Whether to cache allows but never denies.

    Off by default. Turning it on trades a slightly slower deny path for
    a guarantee that a revoked permission is never served from cache --
    worth it for deployments where policies change often.
    """

    # ---- approvals ------------------------------------------------------

    approval_expiry_hours: int = Field(default=48, ge=1, le=8_760)
    """How long a pending approval stays actionable.

    An approval that never expires is a standing grant nobody
    remembers issuing.
    """

    emergency_approval_enabled: bool = Field(default=True)
    """Whether break-glass approvals may be self-granted.

    They are always audited and always notified, which is what makes
    them acceptable at all.
    """

    # ---- quotas ---------------------------------------------------------

    quota_enforcement_enabled: bool = Field(default=True)
    quota_warning_threshold: float = Field(default=0.8, gt=0.0, le=1.0)
    """The fraction of a quota at which a warning is emitted.

    A quota that only speaks when it is exhausted gives an operator no
    chance to act before work starts failing.
    """

    # ---- simulation -----------------------------------------------------

    max_simulation_requests: int = Field(default=1_000, ge=1, le=50_000)
    """How many requests one simulation may evaluate.

    A simulation runs the same engine as a live decision, so an
    unbounded one competes with real authorization for the same process.
    """

    # ---- retention and rollups ------------------------------------------

    decision_retention_days: int = Field(default=90, ge=1)
    violation_retention_days: int = Field(default=365, ge=1)
    """Violations are kept far longer than decisions, deliberately.

    A decision is operational telemetry; a violation is evidence, and
    the question it answers ("when did this start?") is usually asked
    months later.
    """

    scheduler_enabled: bool = Field(default=True)
    statistics_rollup_seconds: int = Field(default=900, ge=60, le=86_400)
    approval_sweep_seconds: int = Field(default=600, ge=60, le=86_400)


@dataclass(frozen=True, slots=True)
class Settings:
    """Every configuration section this service actually uses."""

    application: ApplicationSettings
    database: DatabaseSettings
    redis: RedisSettings
    rabbitmq: RabbitMQSettings
    email: EmailSettings
    service: PolicyEngineServiceSettings


def build_settings(*, service: PolicyEngineServiceSettings | None = None) -> Settings:
    """Build a :class:`Settings`, reusing the shared aggregate's current values."""
    shared = get_shared_settings()
    return Settings(
        application=shared.application,
        database=shared.database,
        redis=shared.redis,
        rabbitmq=shared.rabbitmq,
        email=shared.email,
        service=service if service is not None else PolicyEngineServiceSettings(),
    )


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """The process-wide cached settings, built once."""
    return build_settings()


__all__ = [
    "PolicyEngineServiceSettings",
    "Settings",
    "build_settings",
    "get_settings",
]
