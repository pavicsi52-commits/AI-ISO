"""Pure rotation-policy evaluation: is a secret due for rotation, and
when will it next be due. Per docs/035 "SECRET ROTATION": Scheduled
Rotation, Automatic Rotation.

Deliberately database-independent -- callers in ``app.services`` load
the last-rotated timestamp and persist results; this module only
computes.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any

_DEFAULT_INTERVAL_DAYS = 90


@dataclass(frozen=True, slots=True)
class RotationPolicy:
    """A secret's own rotation policy, parsed from its ``rotation_policy`` JSON."""

    enabled: bool
    interval_days: int

    @classmethod
    def from_json(cls, data: dict[str, Any]) -> RotationPolicy:
        """Parse a :attr:`~app.models.secret.Secret.rotation_policy` blob.

        Missing or malformed fields fall back to disabled / a
        conservative default interval rather than raising -- a secret
        with no rotation policy configured simply never becomes due.
        """
        enabled = bool(data.get("enabled", False))
        interval_days = data.get("interval_days", _DEFAULT_INTERVAL_DAYS)
        if not isinstance(interval_days, int) or interval_days <= 0:
            interval_days = _DEFAULT_INTERVAL_DAYS
        return cls(enabled=enabled, interval_days=interval_days)


def next_rotation_at(policy: RotationPolicy, *, last_rotated_at: datetime) -> datetime:
    """The next time *policy* calls for rotation, measured from *last_rotated_at*."""
    return last_rotated_at + timedelta(days=policy.interval_days)


def is_rotation_due(policy: RotationPolicy, *, last_rotated_at: datetime, now: datetime) -> bool:
    """Whether *policy* calls for rotation as of *now*."""
    if not policy.enabled:
        return False
    return now >= next_rotation_at(policy, last_rotated_at=last_rotated_at)


__all__ = ["RotationPolicy", "is_rotation_due", "next_rotation_at"]
