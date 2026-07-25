"""Configuration validation.

Pydantic already validates types and constraints on load (required/optional,
type, range, enum -- via ``Field()`` constraints on each section). This
module adds cross-cutting checks that only make sense once every section is
loaded together, e.g. "secrets must not be empty in production" and
"a feature that's enabled must have the settings it needs".
"""

from __future__ import annotations

from shared_core.config.environment import Environment
from shared_core.config.exceptions import MissingSecretError
from shared_core.config.loader import Settings
from shared_core.logging import get_logger

logger = get_logger(__name__)

_REQUIRED_IN_PRODUCTION: tuple[tuple[str, str], ...] = (
    ("database", "database_password"),
    ("rabbitmq", "rabbitmq_password"),
    ("neo4j", "neo4j_password"),
    ("minio", "minio_access_key"),
    ("minio", "minio_secret_key"),
)


def validate_settings(settings: Settings) -> None:
    """Validate cross-section configuration invariants.

    Raises:
        MissingSecretError: If a production deployment is missing a
            required secret, whether unconditionally required or required
            because a dependent feature is enabled.
    """
    if settings.application.environment is not Environment.PRODUCTION:
        return

    missing: list[str] = []
    for section_name, field_name in _REQUIRED_IN_PRODUCTION:
        section = getattr(settings, section_name)
        if not getattr(section, field_name):
            missing.append(f"{section_name}.{field_name}")

    if settings.email.email_enabled and not settings.email.smtp_password:
        missing.append("email.smtp_password")
    if settings.ai.ai_provider != "none" and not settings.ai.ai_api_key:
        missing.append("ai.ai_api_key")

    if missing:
        logger.error("config.validate.failure", extra={"missing": missing})
        raise MissingSecretError(missing)
