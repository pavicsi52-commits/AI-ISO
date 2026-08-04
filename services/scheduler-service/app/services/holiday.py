"""Holiday calendar entries, and resolving them into concrete dates."""

from __future__ import annotations

from datetime import date
from uuid import UUID

from app.models.enums import HolidayScope
from app.models.holiday import HolidayCalendarEntry
from app.repositories.holiday import HolidayCalendarRepository


class HolidayService:
    """Holiday calendar entries: authoring, and resolving a year's own dates."""

    def __init__(self, holidays: HolidayCalendarRepository) -> None:
        self._holidays = holidays

    async def create_holiday(
        self,
        organization_id: UUID,
        *,
        name: str,
        holiday_date: date,
        scope: HolidayScope = HolidayScope.ORGANIZATION,
        scope_id: str | None = None,
        is_recurring: bool = True,
        description: str | None = None,
    ) -> HolidayCalendarEntry:
        """Define a holiday."""
        return await self._holidays.create(
            HolidayCalendarEntry(
                organization_id=organization_id,
                scope=scope,
                scope_id=scope_id,
                name=name,
                description=description,
                holiday_date=holiday_date,
                is_recurring=is_recurring,
            )
        )

    async def get(self, organization_id: UUID, holiday_id: UUID) -> HolidayCalendarEntry:
        """One holiday.

        Raises:
            NotFoundError: If it does not exist here.
        """
        return await self._holidays.require_in_org(organization_id, holiday_id)

    async def list_holidays(self, organization_id: UUID) -> list[HolidayCalendarEntry]:
        """Every holiday this organization has defined."""
        return await self._holidays.list_for_org(organization_id)

    async def delete(self, organization_id: UUID, holiday_id: UUID) -> None:
        """Remove a holiday.

        Raises:
            NotFoundError: If it does not exist here.
        """
        stored = await self._holidays.require_in_org(organization_id, holiday_id)
        await self._holidays.delete(stored)

    async def dates_for_year(self, organization_id: UUID, *, year: int) -> frozenset[date]:
        """Every concrete holiday date that applies within *year*."""
        entries = await self._holidays.list_covering_year(organization_id, year=year)
        return self._holidays.to_dates(entries, year=year)


__all__ = ["HolidayService"]
