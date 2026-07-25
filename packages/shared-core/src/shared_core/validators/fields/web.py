"""URL field validation."""

from __future__ import annotations

from urllib.parse import urlparse

from shared_core.validators.results import ValidationResult

_ALLOWED_SCHEMES = frozenset({"http", "https"})


def validate_url(value: str) -> ValidationResult:
    """Validate that ``value`` is a well-formed HTTP(S) URL."""
    try:
        parsed = urlparse(value)
    except ValueError:
        return ValidationResult.fail(f"'{value}' is not a valid URL.")

    if parsed.scheme not in _ALLOWED_SCHEMES or not parsed.netloc:
        return ValidationResult.fail(f"'{value}' is not a valid http(s) URL.")
    return ValidationResult.ok()
