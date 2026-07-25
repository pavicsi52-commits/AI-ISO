"""Email field validation."""

from __future__ import annotations

import re

from shared_core.validators.results import ValidationResult

_EMAIL_PATTERN = re.compile(r"^[^\s@]+@[^\s@]+\.[^\s@]+$")
_MAX_EMAIL_LENGTH = 254


def validate_email(value: str) -> ValidationResult:
    """Validate that ``value`` is a syntactically well-formed email address."""
    if not value or len(value) > _MAX_EMAIL_LENGTH:
        return ValidationResult.fail("Email must be between 1 and 254 characters.")
    if not _EMAIL_PATTERN.match(value):
        return ValidationResult.fail(f"'{value}' is not a valid email address.")
    return ValidationResult.ok()
