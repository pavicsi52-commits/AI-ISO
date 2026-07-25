"""UUID helper functions."""

from __future__ import annotations

import uuid


def generate_uuid() -> uuid.UUID:
    """Generate a new random UUID v4."""
    return uuid.uuid4()


def is_valid_uuid(value: str) -> bool:
    """Return whether ``value`` parses as a UUID."""
    try:
        uuid.UUID(value)
    except (ValueError, AttributeError, TypeError):
        return False
    return True


def short_uuid(value: uuid.UUID | None = None) -> str:
    """Return the first 8 hex characters of a UUID, useful for log correlation."""
    return str(value or uuid.uuid4()).split("-")[0]
