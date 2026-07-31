"""Compliance service settings.

Composes ``shared_core.config``'s aggregate with the fields specific to
this service: host/port, CORS, JWT verification key, and the knobs that
bound assessment, evidence retention, and scoring.

**An assessment walks the whole estate.** Every ceiling below exists
because an unbounded one turns a scheduled compliance run into an
outage of the very infrastructure it is measuring -- and the failure
mode is particularly nasty, because the run that knocks a service over
is the one nobody is watching at 02:00 on a Sunday.
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


class ComplianceServiceSettings(BaseSettings):
    """Fields specific to this service, not covered by any shared_core section."""

    model_config = SettingsConfigDict(
        env_prefix="AIIOS_COMPLIANCE_SERVICE_", env_file=".env", extra="ignore"
    )

    host: str = Field(default="0.0.0.0")
    port: int = Field(default=8022, ge=1, le=65_535)
    cors_allowed_origins: list[str] = Field(default_factory=list)
    jwt_public_key_path: str = Field(default="keys/jwt_public_key.pem")

    http_client_timeout_seconds: float = Field(default=30.0, gt=0)

    # ---- assessment ceilings ------------------------------------------

    max_controls_per_assessment: int = Field(default=2_000, ge=1, le=20_000)
    """How many controls one run may evaluate.

    Bounded because an organization tracking eight frameworks has
    thousands of controls and the natural implementation -- load them
    all, evaluate them all -- turns a nightly job into a database
    incident.
    """

    max_targets_per_control: int = Field(default=5_000, ge=1, le=100_000)
    """How many assets one control may be evaluated against.

    The multiplier that makes assessments expensive: 2,000 controls
    across 5,000 hosts is ten million verdicts. Both ceilings are needed
    because either one alone can be satisfied while the product is
    still ruinous.
    """

    assessment_concurrency: int = Field(default=8, ge=1, le=64)
    """How many controls are evaluated in parallel.

    docs/051 asks for a parallel assessment engine. This is the width of
    it, and it is bounded because every worker holds a database
    connection: concurrency above the pool size does not go faster, it
    deadlocks.
    """

    max_evaluation_seconds: float = Field(default=300.0, gt=0, le=86_400.0)
    """Wall-clock budget for one assessment before it is cut short.

    A run that exceeds it finishes as ``PARTIAL`` rather than being
    discarded -- half an assessment honestly labelled is worth more than
    none, and far more than a whole one that never terminates.
    """

    # ---- evidence -----------------------------------------------------

    evidence_retention_days: int = Field(default=2_555, ge=1, le=36_500)
    """How long evidence is kept. Seven years by default, which is what
    most of the frameworks this service implements actually require --
    a shorter default would quietly make an organization non-compliant
    in the one dimension this service is supposed to guarantee."""

    evidence_default_validity_days: int = Field(default=90, ge=1, le=3_650)
    """How long a new piece of evidence is considered current. A
    configuration snapshot from eighteen months ago does not describe
    today's estate, and an audit package built from stale evidence fails
    in the room."""

    max_evidence_payload_bytes: int = Field(default=1_048_576, ge=1_024, le=67_108_864)
    """Ceiling on an inline evidence payload. Larger artefacts belong in
    object storage with only their key and digest stored here."""

    verify_evidence_on_read: bool = Field(default=False)
    """Recompute every evidence digest when listing.

    Off by default because it makes listing O(payload) rather than
    O(rows), and on by default in an audit-preparation window is exactly
    the right trade. Individual reads always verify.
    """

    # ---- findings and exceptions ---------------------------------------

    finding_due_days_critical: int = Field(default=7, ge=1, le=365)
    finding_due_days_high: int = Field(default=30, ge=1, le=365)
    finding_due_days_medium: int = Field(default=90, ge=1, le=730)
    finding_due_days_low: int = Field(default=180, ge=1, le=1_095)

    max_exception_days: int = Field(default=365, ge=1, le=3_650)
    """The longest a temporary exception may run before re-approval.

    A ceiling rather than a default, because "temporary" is the word
    people use for the exceptions that outlive the systems they were
    granted for.
    """

    exception_review_interval_days: int = Field(default=90, ge=1, le=730)
    exception_expiry_warning_days: int = Field(default=14, ge=1, le=180)

    # ---- risk and scoring ----------------------------------------------

    risk_review_interval_days: int = Field(default=90, ge=1, le=730)
    score_history_days: int = Field(default=365, ge=1, le=3_650)

    minimum_controls_for_score: int = Field(default=1, ge=1, le=1_000)
    """How many scored controls a framework needs before its score is
    published. A framework with one assessed control out of 300 can
    report 100%, and that number will be quoted."""

    # ---- reporting and workers ------------------------------------------

    max_report_rows: int = Field(default=10_000, ge=1, le=1_000_000)
    report_retention_days: int = Field(default=365, ge=1, le=3_650)

    scheduler_enabled: bool = Field(default=True)
    continuous_assessment_seconds: int = Field(default=3_600, ge=60, le=86_400)
    scoring_rollup_seconds: int = Field(default=900, ge=60, le=86_400)
    exception_sweep_seconds: int = Field(default=3_600, ge=60, le=86_400)


@dataclass(frozen=True, slots=True)
class Settings:
    """Every configuration section this service actually uses."""

    application: ApplicationSettings
    database: DatabaseSettings
    redis: RedisSettings
    rabbitmq: RabbitMQSettings
    email: EmailSettings
    service: ComplianceServiceSettings


def build_settings(*, service: ComplianceServiceSettings | None = None) -> Settings:
    """Build a :class:`Settings`, reusing the shared aggregate's current values."""
    shared = get_shared_settings()
    return Settings(
        application=shared.application,
        database=shared.database,
        redis=shared.redis,
        rabbitmq=shared.rabbitmq,
        email=shared.email,
        service=service if service is not None else ComplianceServiceSettings(),
    )


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """The process-wide cached settings, built once."""
    return build_settings()


__all__ = [
    "ComplianceServiceSettings",
    "Settings",
    "build_settings",
    "get_settings",
]
