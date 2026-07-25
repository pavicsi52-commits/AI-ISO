"""Small, dependency-free utility functions shared across the framework."""

from __future__ import annotations

_SENSITIVE_KEYWORDS: tuple[str, ...] = ("password", "token", "secret", "api_key", "apikey")
_MASKED_VALUE = "***MASKED***"


def mask_sensitive_metadata(metadata: dict[str, object]) -> dict[str, object]:
    """Mask any metadata value whose key looks like it carries a secret ("Mask Sensitive Data").

    Matches by keyword against the key name, the same approach
    :func:`shared_core.telemetry.span.sanitize_attributes` uses for span
    attributes -- consistent masking behavior across frameworks.
    """
    return {
        key: (_MASKED_VALUE if any(word in key.lower() for word in _SENSITIVE_KEYWORDS) else value)
        for key, value in metadata.items()
    }


def truncate(text: str, *, max_length: int) -> str:
    """Truncate *text* to *max_length* characters, appending an ellipsis if shortened."""
    if len(text) <= max_length:
        return text
    return text[: max_length - 1] + "…"


def mask_email(email: str) -> str:
    """Mask an email address for logging (``a***@example.com``), keeping the domain visible."""
    local, _at, domain = email.partition("@")
    if not domain:
        return _MASKED_VALUE
    visible = local[:1] or "*"
    return f"{visible}***@{domain}"


__all__ = ["mask_email", "mask_sensitive_metadata", "truncate"]
