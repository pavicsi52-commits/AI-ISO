"""UUID field validation."""

from __future__ import annotations

from uuid import UUID

from shared_core.validators.results import ValidationResult


def validate_uuid(value: str) -> ValidationResult:
    """Validate that ``value`` is a well-formed UUID string."""
    try:
        UUID(value)
    except (ValueError, AttributeError, TypeError):
        return ValidationResult.fail(f"'{value}' is not a valid UUID.")
    return ValidationResult.ok()
