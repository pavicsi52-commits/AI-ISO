"""Date/time helper functions."""

from __future__ import annotations

from datetime import UTC, date, datetime


def utcnow() -> datetime:
    """Return the current UTC time as a timezone-aware datetime."""
    return datetime.now(UTC)


def to_iso8601(value: datetime) -> str:
    """Serialize a datetime to an ISO-8601 string."""
    return value.isoformat()


def from_iso8601(value: str) -> datetime:
    """Parse an ISO-8601 string into a datetime."""
    return datetime.fromisoformat(value)


def is_expired(expires_at: datetime, *, now: datetime | None = None) -> bool:
    """Return whether ``expires_at`` is in the past relative to ``now``."""
    return (now or utcnow()) >= expires_at


def days_between(start: date, end: date) -> int:
    """Return the number of days between two dates."""
    return (end - start).days
