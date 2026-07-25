"""Availability tracking.

Per docs/023_Enterprise_Monitoring_Framework.md.txt "AVAILABILITY":
Current Availability, Historical Availability, Daily/Weekly/Monthly/
Quarterly/Yearly, Availability Percentage.

Purely in-process (this framework must not create business/persistence
tables -- docs/023 "DO NOT IMPLEMENT"): tracks uptime/downtime
transitions for this process's own lifetime. A service wanting
availability history that survives a restart, or bucketed into
calendar days/weeks/months, is expected to feed
:meth:`AvailabilityTracker.record`'s transitions into its own
persistence layer (a genuine business concern this framework must not
own), not something built here.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field

from shared_core.enums.health_status import HealthStatus

_UP_STATUSES = frozenset({HealthStatus.HEALTHY, HealthStatus.DEGRADED, HealthStatus.WARNING})


@dataclass(frozen=True, slots=True)
class AvailabilityWindow:
    """Availability over one observed time window."""

    window_seconds: float
    up_seconds: float
    total_seconds: float

    @property
    def percentage(self) -> float:
        """Availability percentage in ``[0.0, 100.0]``; ``100.0`` if no time has passed."""
        if self.total_seconds <= 0:
            return 100.0
        return (self.up_seconds / self.total_seconds) * 100.0


@dataclass(slots=True)
class AvailabilityTracker:
    """Tracks uptime/downtime transitions and computes availability since the first known status."""

    _current_status: HealthStatus = HealthStatus.UNKNOWN
    _since: float = field(default_factory=time.monotonic)
    _up_seconds: float = 0.0
    _down_seconds: float = 0.0

    def record(self, status: HealthStatus) -> None:
        """Record a newly observed status, closing out the time spent in the previous one."""
        now = time.monotonic()
        elapsed = now - self._since
        if self._current_status in _UP_STATUSES:
            self._up_seconds += elapsed
        elif self._current_status is not HealthStatus.UNKNOWN:
            self._down_seconds += elapsed
        self._current_status = status
        self._since = now

    def _totals(self) -> tuple[float, float]:
        """Return ``(up_seconds, down_seconds)`` including time in the current status so far."""
        now = time.monotonic()
        elapsed = now - self._since
        up, down = self._up_seconds, self._down_seconds
        if self._current_status in _UP_STATUSES:
            up += elapsed
        elif self._current_status is not HealthStatus.UNKNOWN:
            down += elapsed
        return up, down

    def current_window(self) -> AvailabilityWindow:
        """Availability since the first known status was recorded ("Current Availability").

        Time before the first :meth:`record` call (while status is still
        ``UNKNOWN``) counts toward neither up nor down time, so a
        freshly constructed tracker reports ``100.0`` (via
        :attr:`AvailabilityWindow.percentage`'s own "no time has passed"
        default) rather than a misleading near-zero reading.
        """
        up, down = self._totals()
        total = up + down
        return AvailabilityWindow(window_seconds=total, up_seconds=up, total_seconds=total)

    @property
    def availability_percentage(self) -> float:
        """Shorthand for ``current_window().percentage`` ("Availability Percentage")."""
        return self.current_window().percentage


__all__ = ["AvailabilityTracker", "AvailabilityWindow"]
