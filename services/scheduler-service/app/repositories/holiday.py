"""The holiday calendar repository."""

from __future__ import annotations

from datetime import date
from uuid import UUID

from shared_core.database.repository import BaseRepository
from shared_core.database.tenant import TenantScope
from shared_core.exceptions.not_found import NotFoundError
from sqlalchemy import extract, or_
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.holiday import HolidayCalendarEntry


class HolidayCalendarRepository(BaseRepository[HolidayCalendarEntry]):
    """Non-working days for ``BUSINESS_DAYS``-aware scheduling."""

    def __init__(self, session: AsyncSession, *, tenant_scope: TenantScope | None = None) -> None:
        super().__init__(session, HolidayCalendarEntry, tenant_scope=tenant_scope)

    async def require_in_org(self, organization_id: UUID, holiday_id: UUID) -> HolidayCalendarEntry:
        """One holiday by id, scoped to its organization.

        Raises:
            NotFoundError: If it does not exist here.
        """
        stmt = (
            self._base_select()
            .where(HolidayCalendarEntry.organization_id == organization_id)
            .where(HolidayCalendarEntry.id == holiday_id)
        )
        result = await self._session.execute(stmt)
        found: HolidayCalendarEntry | None = result.scalars().first()
        if found is None:
            raise NotFoundError(f"No holiday with id {holiday_id} in this organization.")
        return found

    async def list_for_org(
        self, organization_id: UUID, *, limit: int = 500
    ) -> list[HolidayCalendarEntry]:
        """Every holiday this organization has defined."""
        stmt = (
            self._base_select()
            .where(HolidayCalendarEntry.organization_id == organization_id)
            .order_by(HolidayCalendarEntry.holiday_date)
            .limit(limit)
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def list_covering_year(
        self, organization_id: UUID, *, year: int, limit: int = 500
    ) -> list[HolidayCalendarEntry]:
        """Every holiday that applies within *year*.

        A recurring entry applies to every year (its own stored year is
        only a reference), so it is matched regardless of *year*; a
        one-off exception only matches its own exact year.
        """
        stmt = (
            self._base_select()
            .where(HolidayCalendarEntry.organization_id == organization_id)
            .where(
                or_(
                    HolidayCalendarEntry.is_recurring.is_(True),
                    extract("year", HolidayCalendarEntry.holiday_date) == year,
                )
            )
            .limit(limit)
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    @staticmethod
    def to_dates(entries: list[HolidayCalendarEntry], *, year: int) -> frozenset[date]:
        """Every entry's own concrete date within *year*.

        A recurring entry's month/day repeat into *year*; a non-recurring
        one contributes its exact stored date only, and only if that date
        actually falls in *year* -- a one-off exception from a different
        year is not a holiday here.
        """
        dates: set[date] = set()
        for entry in entries:
            if entry.is_recurring:
                try:
                    dates.add(entry.holiday_date.replace(year=year))
                except ValueError:
                    # Feb 29 on a non-leap year -- there is no such date
                    # to observe the holiday on that year.
                    continue
            elif entry.holiday_date.year == year:
                dates.add(entry.holiday_date)
        return frozenset(dates)


__all__ = ["HolidayCalendarRepository"]
