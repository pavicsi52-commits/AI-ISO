"""Validation result status enumeration."""

from enum import StrEnum


class ValidationStatus(StrEnum):
    """Outcome of a validation pipeline run."""

    VALID = "valid"
    INVALID = "invalid"
    WARNING = "warning"
