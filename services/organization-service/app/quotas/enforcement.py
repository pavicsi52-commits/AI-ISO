"""Quota enforcement: pure comparison of current usage against a configured cap.

Per docs/033 "SECURITY": "Enforce quotas." A pure function operating on
plain integers -- no database access -- so the decision logic is
directly unit-testable independent of how "current usage" gets
computed (member count today; asset/workflow/etc. counts once those
services exist, via ``organization_statistics``).
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class QuotaCheckResult:
    """The outcome of comparing current usage against a configured quota."""

    within_quota: bool
    current: int
    maximum: int

    @property
    def remaining(self) -> int:
        """How much headroom is left (never negative)."""
        return max(0, self.maximum - self.current)


def check_quota(*, current: int, maximum: int) -> QuotaCheckResult:
    """Whether *current* usage is still within *maximum* ("Enforce quotas").

    A *maximum* of ``0`` or below means "unlimited" -- always within quota.
    """
    if maximum <= 0:
        return QuotaCheckResult(within_quota=True, current=current, maximum=maximum)
    return QuotaCheckResult(within_quota=current < maximum, current=current, maximum=maximum)


__all__ = ["QuotaCheckResult", "check_quota"]
