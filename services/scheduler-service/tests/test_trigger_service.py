"""TriggerService: trigger management, and recomputing each job's own next-due state.

Against real PostgreSQL, in a SAVEPOINT-isolated session per test.
"""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from uuid import uuid4

import pytest
from shared_core.exceptions.not_found import NotFoundError
from shared_core.exceptions.validation import ValidationError

from app.models.enums import CalendarRuleKind, HolidayScope
from app.models.holiday import HolidayCalendarEntry
from app.services.trigger import TriggerService

pytestmark = pytest.mark.asyncio

_FIXED_NOW = datetime(2026, 8, 3, 12, 0, tzinfo=UTC)
"""A Monday noon -- deterministic base moment for every recompute in this module."""


async def _add_holiday(holidays_repo, organization_id, *, on: date) -> None:
    await holidays_repo.create(
        HolidayCalendarEntry(
            organization_id=organization_id,
            scope=HolidayScope.ORGANIZATION,
            name="Test holiday",
            holiday_date=on,
            is_recurring=False,
        )
    )


class TestAddTrigger:
    async def test_raises_not_found_if_the_job_does_not_exist(
        self, trigger_service: TriggerService, organization_id
    ) -> None:
        with pytest.raises(NotFoundError):
            await trigger_service.add_trigger(
                organization_id, uuid4(), trigger_type="cron", cron_expression="0 2 * * *"
            )

    async def test_attaches_a_trigger_and_computes_the_schedule(
        self, trigger_service: TriggerService, organization_id, make_job, schedules_repo
    ) -> None:
        job = await make_job("Nightly sync")
        created = await trigger_service.add_trigger(
            organization_id, job.id, trigger_type="cron", cron_expression="0 2 * * *"
        )
        assert created.job_id == job.id
        assert created.enabled is True
        schedule = await schedules_repo.get_for_job(organization_id, job.id)
        assert schedule is not None
        assert schedule.next_run_at is not None

    async def test_creates_a_disabled_trigger_when_requested(
        self, trigger_service: TriggerService, organization_id, make_job
    ) -> None:
        job = await make_job()
        created = await trigger_service.add_trigger(
            organization_id,
            job.id,
            trigger_type="cron",
            cron_expression="0 2 * * *",
            enabled=False,
        )
        assert created.enabled is False

    async def test_publishes_a_job_scheduled_event(
        self, trigger_service: TriggerService, organization_id, make_job, publisher
    ) -> None:
        job = await make_job()
        await trigger_service.add_trigger(
            organization_id, job.id, trigger_type="cron", cron_expression="0 2 * * *"
        )
        assert "JobScheduled" in publisher.names


class TestNoComputedNextRunTriggerTypes:
    async def test_these_trigger_types_never_produce_a_next_run_at(
        self, trigger_service: TriggerService, organization_id, make_job, schedules_repo
    ) -> None:
        for trigger_type in (
            "manual_trigger",
            "dependency_driven",
            "event_driven",
            "maintenance_window",
        ):
            job = await make_job(f"Job for {trigger_type}")
            await trigger_service.add_trigger(organization_id, job.id, trigger_type=trigger_type)
            schedule = await schedules_repo.get_for_job(organization_id, job.id)
            assert schedule is not None
            assert schedule.next_run_at is None


class TestListTriggers:
    async def test_lists_every_trigger_registered_for_a_job(
        self, trigger_service: TriggerService, organization_id, make_job
    ) -> None:
        job = await make_job()
        await trigger_service.add_trigger(
            organization_id, job.id, trigger_type="cron", cron_expression="0 2 * * *"
        )
        await trigger_service.add_trigger(
            organization_id, job.id, trigger_type="interval", interval_seconds=3_600
        )
        found = await trigger_service.list_triggers(organization_id, job.id)
        assert len(found) == 2
        assert {one.trigger_type for one in found} == {"cron", "interval"}


class TestSetEnabled:
    async def test_raises_not_found_for_a_missing_trigger(
        self, trigger_service: TriggerService, organization_id
    ) -> None:
        with pytest.raises(NotFoundError):
            await trigger_service.set_enabled(organization_id, uuid4(), enabled=False)

    async def test_disabling_the_only_trigger_clears_the_jobs_next_run_at(
        self, trigger_service: TriggerService, organization_id, make_job, schedules_repo
    ) -> None:
        job = await make_job()
        created = await trigger_service.add_trigger(
            organization_id, job.id, trigger_type="cron", cron_expression="0 2 * * *"
        )
        await trigger_service.set_enabled(organization_id, created.id, enabled=False)
        schedule = await schedules_repo.get_for_job(organization_id, job.id)
        assert schedule is not None
        assert schedule.next_run_at is None

    async def test_re_enabling_a_trigger_recomputes_a_next_run_at(
        self, trigger_service: TriggerService, organization_id, make_job, schedules_repo
    ) -> None:
        job = await make_job()
        created = await trigger_service.add_trigger(
            organization_id,
            job.id,
            trigger_type="cron",
            cron_expression="0 2 * * *",
            enabled=False,
        )
        await trigger_service.set_enabled(organization_id, created.id, enabled=True)
        schedule = await schedules_repo.get_for_job(organization_id, job.id)
        assert schedule is not None
        assert schedule.next_run_at is not None


class TestRemove:
    async def test_raises_not_found_for_a_missing_trigger(
        self, trigger_service: TriggerService, organization_id
    ) -> None:
        with pytest.raises(NotFoundError):
            await trigger_service.remove(organization_id, uuid4())

    async def test_removes_a_trigger_and_recomputes_the_schedule(
        self, trigger_service: TriggerService, organization_id, make_job, schedules_repo
    ) -> None:
        job = await make_job()
        created = await trigger_service.add_trigger(
            organization_id, job.id, trigger_type="cron", cron_expression="0 2 * * *"
        )
        await trigger_service.remove(organization_id, created.id)

        remaining = await trigger_service.list_triggers(organization_id, job.id)
        assert remaining == []
        schedule = await schedules_repo.get_for_job(organization_id, job.id)
        assert schedule is not None
        assert schedule.next_run_at is None


class TestRecomputeSchedule:
    async def test_takes_the_earliest_next_run_across_every_enabled_trigger(
        self, trigger_service: TriggerService, organization_id, make_job
    ) -> None:
        job = await make_job("Multi-trigger job")
        await trigger_service.add_trigger(
            organization_id, job.id, trigger_type="cron", cron_expression="0 2 * * *"
        )
        await trigger_service.add_trigger(
            organization_id, job.id, trigger_type="interval", interval_seconds=60
        )
        schedule = await trigger_service.recompute_schedule(organization_id, job.id, now=_FIXED_NOW)
        assert schedule.next_run_at == _FIXED_NOW + timedelta(seconds=60)

    async def test_ignores_disabled_triggers_when_computing_the_earliest(
        self, trigger_service: TriggerService, organization_id, make_job
    ) -> None:
        job = await make_job("Job with a disabled trigger")
        await trigger_service.add_trigger(
            organization_id,
            job.id,
            trigger_type="cron",
            cron_expression="* * * * *",
            enabled=False,
        )
        await trigger_service.add_trigger(
            organization_id, job.id, trigger_type="interval", interval_seconds=3_600
        )
        schedule = await trigger_service.recompute_schedule(organization_id, job.id, now=_FIXED_NOW)
        assert schedule.next_run_at == _FIXED_NOW + timedelta(hours=1)

    async def test_publishes_job_scheduled_even_when_the_result_is_none(
        self, trigger_service: TriggerService, organization_id, make_job, publisher
    ) -> None:
        job = await make_job("Manual only job")
        publisher.events.clear()
        await trigger_service.add_trigger(organization_id, job.id, trigger_type="manual_trigger")
        assert "JobScheduled" in publisher.names
        last_event = publisher.events[-1]
        assert last_event.payload["next_run_at"] is None

    async def test_raises_not_found_if_the_job_does_not_exist(
        self, trigger_service: TriggerService, organization_id
    ) -> None:
        with pytest.raises(NotFoundError):
            await trigger_service.recompute_schedule(organization_id, uuid4())


class TestCalendarCustomRule:
    async def test_custom_calendar_rule_requires_a_cron_expression_key(
        self, trigger_service: TriggerService, organization_id, make_job
    ) -> None:
        job = await make_job()
        with pytest.raises(ValidationError):
            await trigger_service.add_trigger(
                organization_id,
                job.id,
                trigger_type="calendar",
                calendar_rule=CalendarRuleKind.CUSTOM,
                calendar_config={},
            )

    async def test_custom_calendar_rule_computes_from_its_own_cron_expression(
        self, trigger_service: TriggerService, organization_id, make_job
    ) -> None:
        job = await make_job()
        await trigger_service.add_trigger(
            organization_id,
            job.id,
            trigger_type="custom_schedule",
            calendar_rule=CalendarRuleKind.CUSTOM,
            calendar_config={"cron_expression": "*/15 * * * *"},
        )
        schedule = await trigger_service.recompute_schedule(organization_id, job.id, now=_FIXED_NOW)
        assert schedule.next_run_at is not None


class TestHolidaySkipping:
    async def test_business_days_calendar_trigger_skips_a_configured_holiday(
        self, trigger_service: TriggerService, organization_id, make_job, holidays_repo
    ) -> None:
        job = await make_job("Business days job")
        await trigger_service.add_trigger(
            organization_id,
            job.id,
            trigger_type="calendar",
            calendar_rule=CalendarRuleKind.BUSINESS_DAYS,
            calendar_config={"hour": 2, "minute": 0},
        )
        # The plain next business-day fire from a Monday noon is Tuesday
        # 02:00 -- make that exact date a holiday.
        await _add_holiday(holidays_repo, organization_id, on=date(2026, 8, 4))

        schedule = await trigger_service.recompute_schedule(organization_id, job.id, now=_FIXED_NOW)
        assert schedule.next_run_at is not None
        assert schedule.next_run_at.date() == date(2026, 8, 5)

    async def test_a_plain_cron_trigger_never_skips_holidays(
        self, trigger_service: TriggerService, organization_id, make_job, holidays_repo
    ) -> None:
        job = await make_job("Cron job")
        await trigger_service.add_trigger(
            organization_id, job.id, trigger_type="cron", cron_expression="0 2 * * *"
        )
        await _add_holiday(holidays_repo, organization_id, on=date(2026, 8, 4))

        schedule = await trigger_service.recompute_schedule(organization_id, job.id, now=_FIXED_NOW)
        assert schedule.next_run_at is not None
        assert schedule.next_run_at.date() == date(2026, 8, 4)

    async def test_a_calendar_trigger_with_a_different_rule_never_skips_holidays(
        self, trigger_service: TriggerService, organization_id, make_job, holidays_repo
    ) -> None:
        job = await make_job("Daily calendar job")
        await trigger_service.add_trigger(
            organization_id,
            job.id,
            trigger_type="calendar",
            calendar_rule=CalendarRuleKind.DAILY,
            calendar_config={"hour": 2, "minute": 0},
        )
        await _add_holiday(holidays_repo, organization_id, on=date(2026, 8, 4))

        schedule = await trigger_service.recompute_schedule(organization_id, job.id, now=_FIXED_NOW)
        assert schedule.next_run_at is not None
        assert schedule.next_run_at.date() == date(2026, 8, 4)
