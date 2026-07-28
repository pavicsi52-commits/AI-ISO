"""Availability interval tracking ("AVAILABILITY" "Track": Uptime,
Downtime, Availability Percentage, Maintenance Windows, Outages,
Recovery Time, Historical Availability).

:meth:`record_status` is the single entry point every collection run
calls: it closes the target's own currently open interval (if its
status differs from the newly observed one) and opens a fresh one,
rather than exposing separate "open"/"close" actions callers would need
to sequence correctly themselves.
"""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID

from app.models.enums import AvailabilityStatus
from app.models.monitoring_availability import MonitoringAvailability
from app.repositories.monitoring_availability import MonitoringAvailabilityRepository


class MonitoringAvailabilityService:
    """Tracks and reads target availability intervals."""

    def __init__(self, availability: MonitoringAvailabilityRepository) -> None:
        self._availability = availability

    async def list_for_target(self, target_id: UUID) -> list[MonitoringAvailability]:
        """Every availability interval recorded for *target_id*, oldest first."""
        return await self._availability.list_for_target(target_id)

    async def get_current_for_target(self, target_id: UUID) -> MonitoringAvailability | None:
        """Return *target_id*'s own still-open interval, if any."""
        return await self._availability.get_current_for_target(target_id)

    async def record_status(
        self,
        *,
        organization_id: UUID,
        target_id: UUID,
        status: AvailabilityStatus,
        observed_at: datetime | None = None,
    ) -> MonitoringAvailability:
        """Record *target_id*'s own newly observed availability *status*.

        A no-op (returns the already-open interval unchanged) if it
        matches the currently open interval's own status; otherwise
        closes the current interval and opens a new one.
        """
        now = observed_at or datetime.now(UTC)
        current = await self._availability.get_current_for_target(target_id)
        if current is not None and current.status == status:
            return current
        if current is not None:
            current.ended_at = now
            current.duration_seconds = (now - current.started_at).total_seconds()
            await self._availability.update(current)
        return await self._availability.create(
            MonitoringAvailability(
                organization_id=organization_id,
                target_id=target_id,
                status=status,
                started_at=now,
                ended_at=None,
                duration_seconds=None,
            )
        )


__all__ = ["MonitoringAvailabilityService"]
