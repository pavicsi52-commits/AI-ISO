"""HolidayService: authoring holidays, and resolving a year's own dates.

Against real PostgreSQL, in a SAVEPOINT-isolated session per test.
"""

from __future__ import annotations

from datetime import date
from uuid import uuid4

import pytest
from shared_core.exceptions.not_found import NotFoundError

from app.models.enums import HolidayScope
from app.services.holiday import HolidayService

pytestmark = pytest.mark.asyncio


class TestCreateHoliday:
    async def test_creates_a_recurring_holiday(
        self, holiday_service: HolidayService, organization_id
    ) -> None:
        created = await holiday_service.create_holiday(
            organization_id, name="Christmas", holiday_date=date(2020, 12, 25)
        )
        assert created.name == "Christmas"
        assert created.is_recurring is True
        assert created.scope == HolidayScope.ORGANIZATION

    async def test_creates_a_non_recurring_exception(
        self, holiday_service: HolidayService, organization_id
    ) -> None:
        created = await holiday_service.create_holiday(
            organization_id,
            name="One-off closure",
            holiday_date=date(2026, 3, 15),
            is_recurring=False,
        )
        assert created.is_recurring is False

    async def test_creates_a_regional_holiday_with_a_scope_id(
        self, holiday_service: HolidayService, organization_id
    ) -> None:
        created = await holiday_service.create_holiday(
            organization_id,
            name="Regional day",
            holiday_date=date(2020, 7, 4),
            scope=HolidayScope.REGIONAL,
            scope_id="US",
        )
        assert created.scope == HolidayScope.REGIONAL
        assert created.scope_id == "US"


class TestGetAndList:
    async def test_get_raises_not_found_for_a_missing_holiday(
        self, holiday_service: HolidayService, organization_id
    ) -> None:
        with pytest.raises(NotFoundError):
            await holiday_service.get(organization_id, uuid4())

    async def test_get_is_scoped_to_its_organization(
        self, holiday_service: HolidayService, organization_id
    ) -> None:
        created = await holiday_service.create_holiday(
            organization_id, name="Christmas", holiday_date=date(2020, 12, 25)
        )
        with pytest.raises(NotFoundError):
            await holiday_service.get(uuid4(), created.id)

    async def test_list_holidays_returns_every_holiday_for_the_org(
        self, holiday_service: HolidayService, organization_id
    ) -> None:
        await holiday_service.create_holiday(
            organization_id, name="A", holiday_date=date(2020, 1, 1)
        )
        await holiday_service.create_holiday(
            organization_id, name="B", holiday_date=date(2020, 6, 1)
        )
        found = await holiday_service.list_holidays(organization_id)
        assert len(found) >= 2

    async def test_list_holidays_excludes_other_organizations(
        self, holiday_service: HolidayService, organization_id
    ) -> None:
        await holiday_service.create_holiday(
            uuid4(), name="Someone else's holiday", holiday_date=date(2020, 1, 1)
        )
        found = await holiday_service.list_holidays(organization_id)
        assert found == []


class TestDelete:
    async def test_removes_a_holiday(
        self, holiday_service: HolidayService, organization_id
    ) -> None:
        created = await holiday_service.create_holiday(
            organization_id, name="Christmas", holiday_date=date(2020, 12, 25)
        )
        await holiday_service.delete(organization_id, created.id)
        with pytest.raises(NotFoundError):
            await holiday_service.get(organization_id, created.id)

    async def test_delete_raises_not_found_for_a_missing_holiday(
        self, holiday_service: HolidayService, organization_id
    ) -> None:
        with pytest.raises(NotFoundError):
            await holiday_service.delete(organization_id, uuid4())


class TestDatesForYear:
    async def test_a_recurring_holiday_resolves_into_the_requested_year(
        self, holiday_service: HolidayService, organization_id
    ) -> None:
        await holiday_service.create_holiday(
            organization_id, name="Christmas", holiday_date=date(2020, 12, 25), is_recurring=True
        )
        dates = await holiday_service.dates_for_year(organization_id, year=2026)
        assert date(2026, 12, 25) in dates

    async def test_a_non_recurring_holiday_only_appears_in_its_own_year(
        self, holiday_service: HolidayService, organization_id
    ) -> None:
        await holiday_service.create_holiday(
            organization_id,
            name="One-off closure",
            holiday_date=date(2026, 3, 15),
            is_recurring=False,
        )
        this_year = await holiday_service.dates_for_year(organization_id, year=2026)
        other_year = await holiday_service.dates_for_year(organization_id, year=2027)
        assert date(2026, 3, 15) in this_year
        assert date(2026, 3, 15) not in other_year
        assert not any(one.year == 2027 for one in other_year if one == date(2026, 3, 15))

    async def test_no_holidays_returns_an_empty_set(
        self, holiday_service: HolidayService, organization_id
    ) -> None:
        dates = await holiday_service.dates_for_year(organization_id, year=2026)
        assert dates == frozenset()

    async def test_a_recurring_feb_29_holiday_does_not_crash_on_a_non_leap_year(
        self, holiday_service: HolidayService, organization_id
    ) -> None:
        await holiday_service.create_holiday(
            organization_id, name="Leap day", holiday_date=date(2020, 2, 29), is_recurring=True
        )
        dates = await holiday_service.dates_for_year(organization_id, year=2026)
        assert all(one.year == 2026 for one in dates)
