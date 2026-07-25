"""Logging-related constants."""

from typing import Final


class LoggingConstants:
    """Logging framework constants."""

    DEFAULT_LOG_LEVEL: Final[str] = "INFO"
    MAX_LOG_FILE_SIZE_MB: Final[int] = 100
    LOG_RETENTION_DAYS: Final[int] = 90
    MASKED_VALUE: Final[str] = "***MASKED***"

    SENSITIVE_FIELD_NAMES: Final[frozenset[str]] = frozenset(
        {
            "password",
            "secret",
            "token",
            "api_key",
            "apikey",
            "authorization",
            "jwt",
            "private_key",
            "credit_card",
            "ssn",
        }
    )
