"""Maintenance windows and blackout periods: creating entries, checking availability.

Wraps ``app/calendar/engine.py`` with the database.
"""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from shared_core.logging.logger import get_logger

from app.calendar.engine import AvailabilityCheck, check_availability, expand_occurrences
from app.models.calendar import ChangeCalendarEntry
from app.models.enums import CalendarEntryKind, RecurrenceKind, recurrence_kind_of
from app.repositories.calendar import ChangeCalendarRepository

logger = get_logger("app.services.calendar")


class CalendarService:
    """Maintenance windows and blackout periods."""

    def __init__(self, calendar: ChangeCalendarRepository) -> None:
        self._calendar = calendar

    async def create_entry(
        self,
        organization_id: UUID,
        *,
        kind: CalendarEntryKind,
        title: str,
        starts_at: datetime,
        ends_at: datetime,
        description: str | None = None,
        timezone: str = "UTC",
        recurrence: RecurrenceKind = RecurrenceKind.NONE,
        recurrence_until: datetime | None = None,
        is_org_wide: bool = True,
        capacity_limit: int | None = None,
        actor_id: UUID | None = None,
    ) -> ChangeCalendarEntry:
        """Create a maintenance window or blackout period."""
        return await self._calendar.create(
            ChangeCalendarEntry(
                organization_id=organization_id,
                kind=kind,
                title=title,
                description=description,
                starts_at=starts_at,
                ends_at=ends_at,
                timezone=timezone,
                recurrence=recurrence,
                recurrence_until=recurrence_until,
                is_org_wide=is_org_wide,
                capacity_limit=capacity_limit,
                created_by=actor_id,
            )
        )

    async def get(self, organization_id: UUID, entry_id: UUID) -> ChangeCalendarEntry:
        """One calendar entry.

        Raises:
            NotFoundError: If it does not exist here.
        """
        return await self._calendar.require_in_org(organization_id, entry_id)

    async def list_occurrences_in_range(
        self,
        organization_id: UUID,
        *,
        start: datetime,
        end: datetime,
        kind: CalendarEntryKind | None = None,
    ) -> list[tuple[ChangeCalendarEntry, list[tuple[datetime, datetime]]]]:
        """Every calendar entry with at least one occurrence touching a range.

        Each entry is paired with its own expanded occurrences within
        the range -- a recurring entry only shows the concrete dates
        that actually fall inside the window a caller asked about, not
        its entire recurrence.
        """
        candidates = await self._calendar.list_overlapping(
            organization_id, start=start, end=end, kind=kind
        )
        results: list[tuple[ChangeCalendarEntry, list[tuple[datetime, datetime]]]] = []
        for entry in candidates:
            occurrences = expand_occurrences(
                starts_at=entry.starts_at,
                ends_at=entry.ends_at,
                recurrence=recurrence_kind_of(entry.recurrence),
                recurrence_until=entry.recurrence_until,
                window_start=start,
                window_end=end,
            )
            if occurrences:
                results.append((entry, occurrences))
        return results

    async def check_availability(
        self, organization_id: UUID, entry_id: UUID, *, exclude_change_id: UUID | None = None
    ) -> AvailabilityCheck:
        """Whether a maintenance window still has capacity for one more change.

        Raises:
            NotFoundError: If the entry does not exist here.
        """
        entry = await self._calendar.require_in_org(organization_id, entry_id)
        current_bookings = await self._calendar.count_bookings(
            organization_id, entry_id, exclude_change_id=exclude_change_id
        )
        return check_availability(
            capacity_limit=entry.capacity_limit, current_bookings=current_bookings
        )


__all__ = ["CalendarService"]
