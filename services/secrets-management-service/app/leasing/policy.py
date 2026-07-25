"""Pure lease expiration/validity logic. Per docs/035 "SECRET LEASING":
Lease Duration, Lease Expiration.
"""

from __future__ import annotations

from datetime import datetime, timedelta


def compute_expiry(*, issued_at: datetime, duration_seconds: int) -> datetime:
    """The timestamp a lease issued at *issued_at* for *duration_seconds* expires at."""
    return issued_at + timedelta(seconds=duration_seconds)


def is_lease_expired(*, expires_at: datetime, now: datetime) -> bool:
    """Whether a lease has passed its expiration time as of *now*."""
    return now >= expires_at


__all__ = ["compute_expiry", "is_lease_expired"]
