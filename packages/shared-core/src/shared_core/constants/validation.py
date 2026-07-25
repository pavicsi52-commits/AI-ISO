"""Validation-related constants."""

from typing import Final


class ValidationConstants:
    """Field length and pattern constants used by validators."""

    NAME_MIN_LENGTH: Final[int] = 2
    NAME_MAX_LENGTH: Final[int] = 100
    USERNAME_MIN_LENGTH: Final[int] = 3
    USERNAME_MAX_LENGTH: Final[int] = 32
    DESCRIPTION_MAX_LENGTH: Final[int] = 2_000

    MAX_VALIDATION_LATENCY_MS: Final[float] = 10.0
    MAX_FIELD_VALIDATION_LATENCY_MS: Final[float] = 1.0
