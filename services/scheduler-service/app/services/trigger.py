"""Trigger management, and recomputing each job's own next-due state.

A job may carry more than one trigger; :meth:`TriggerService.recompute_schedule`
is what collapses them into the single materialized
:class:`~app.models.trigger.JobSchedule` row a sweep actually polls --
the earliest next-due time across every one of a job's *enabled*
triggers.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from shared_core.logging.logger import get_logger

from app.events.scheduler_events import SOURCE_SERVICE, JobScheduledEvent
from app.models.enums import CalendarRuleKind
from app.models.trigger import JobSchedule, JobTrigger
from app.repositories.holiday import HolidayCalendarRepository
from app.repositories.job import ScheduledJobRepository
from app.repositories.trigger import JobScheduleRepository, JobTriggerRepository
from app.scheduling.engine import (
    TriggerInput,
    calendar_rule_to_cron,
    compute_next_run_at,
    next_business_run_at,
)
from app.types import EventPublisher

logger = get_logger("app.services.trigger")


def _to_input(trigger: JobTrigger) -> TriggerInput:
    return TriggerInput(
        trigger_type=str(trigger.trigger_type),
        cron_expression=trigger.cron_expression,
        run_at=trigger.run_at,
        interval_seconds=trigger.interval_seconds,
        calendar_rule=CalendarRuleKind(trigger.calendar_rule) if trigger.calendar_rule else None,
        calendar_config=trigger.calendar_config,
    )


class TriggerService:
    """Declarative trigger rules, and the materialized schedule state they feed."""

    def __init__(
        self,
        triggers: JobTriggerRepository,
        schedules: JobScheduleRepository,
        jobs: ScheduledJobRepository,
        holidays: HolidayCalendarRepository,
        *,
        publish_event: EventPublisher | None = None,
    ) -> None:
        self._triggers = triggers
        self._schedules = schedules
        self._jobs = jobs
        self._holidays = holidays
        self._publish = publish_event

    async def _publish_event(self, event: Any) -> None:
        if self._publish is not None:
            await self._publish(event)

    async def add_trigger(
        self,
        organization_id: UUID,
        job_id: UUID,
        *,
        trigger_type: str,
        cron_expression: str | None = None,
        run_at: datetime | None = None,
        interval_seconds: float | None = None,
        calendar_rule: CalendarRuleKind | None = None,
        calendar_config: dict[str, Any] | None = None,
        event_name: str | None = None,
        description: str | None = None,
        enabled: bool = True,
    ) -> JobTrigger:
        """Attach a new trigger to a job, and recompute its schedule.

        Raises:
            NotFoundError: If the job does not exist here.
        """
        await self._jobs.require_in_org(organization_id, job_id)
        created = await self._triggers.create(
            JobTrigger(
                organization_id=organization_id,
                job_id=job_id,
                trigger_type=trigger_type,
                cron_expression=cron_expression,
                run_at=run_at,
                interval_seconds=interval_seconds,
                calendar_rule=calendar_rule,
                calendar_config=dict(calendar_config or {}),
                event_name=event_name,
                description=description,
                enabled=enabled,
            )
        )
        await self.recompute_schedule(organization_id, job_id)
        return created

    async def list_triggers(self, organization_id: UUID, job_id: UUID) -> list[JobTrigger]:
        """Every trigger registered for one job."""
        return await self._triggers.list_for_job(organization_id, job_id)

    async def set_enabled(
        self, organization_id: UUID, trigger_id: UUID, *, enabled: bool
    ) -> JobTrigger:
        """Enable or disable a trigger, and recompute its job's schedule.

        Raises:
            NotFoundError: If the trigger does not exist here.
        """
        stored = await self._triggers.require_in_org(organization_id, trigger_id)
        stored.enabled = enabled
        updated = await self._triggers.update(stored)
        await self.recompute_schedule(organization_id, stored.job_id)
        return updated

    async def remove(self, organization_id: UUID, trigger_id: UUID) -> None:
        """Remove a trigger, and recompute its job's schedule.

        Raises:
            NotFoundError: If the trigger does not exist here.
        """
        stored = await self._triggers.require_in_org(organization_id, trigger_id)
        job_id = stored.job_id
        await self._triggers.delete(stored)
        await self.recompute_schedule(organization_id, job_id)

    async def recompute_schedule(
        self, organization_id: UUID, job_id: UUID, *, now: datetime | None = None
    ) -> JobSchedule:
        """Recompute and store a job's own next-due time from its enabled triggers.

        The earliest next-due time across every enabled trigger wins --
        a job with both a cron and an event trigger is due the moment
        either one says so. Publishes ``JobScheduled``.
        """
        moment = now or datetime.now(UTC)
        job = await self._jobs.require_in_org(organization_id, job_id)
        triggers = await self._triggers.list_enabled_for_job(organization_id, job_id)

        candidates: list[datetime] = []
        for trigger in triggers:
            next_run = await self._next_run_for(
                organization_id, trigger, now=moment, timezone_name=job.timezone
            )
            if next_run is not None:
                candidates.append(next_run)
        next_run_at = min(candidates) if candidates else None

        existing = await self._schedules.get_for_job(organization_id, job_id)
        schedule = existing or JobSchedule(organization_id=organization_id, job_id=job_id)
        schedule.next_run_at = next_run_at
        schedule.last_evaluated_at = moment
        stored_schedule = (
            await self._schedules.update(schedule)
            if existing
            else await self._schedules.create(schedule)
        )

        job.next_run_at = next_run_at
        await self._jobs.update(job)

        await self._publish_event(
            JobScheduledEvent(
                source_service=SOURCE_SERVICE,
                payload={
                    "organization_id": str(organization_id),
                    "job_id": str(job_id),
                    "next_run_at": next_run_at.isoformat() if next_run_at else None,
                },
            )
        )
        return stored_schedule

    async def _next_run_for(
        self, organization_id: UUID, trigger: JobTrigger, *, now: datetime, timezone_name: str
    ) -> datetime | None:
        """One trigger's own next-due time, holiday-aware for ``BUSINESS_DAYS`` calendar triggers.

        Holiday-skipping is deliberately narrow: a raw cron expression
        (e.g. an hourly heartbeat) makes no promise about calendar days
        at all, and skipping it on a configured holiday would be a
        surprising, unrequested behaviour change. A ``calendar`` trigger
        whose rule is specifically ``BUSINESS_DAYS`` is the one case
        where "skip holidays" is unambiguously what was asked for.
        """
        trigger_input = _to_input(trigger)
        is_business_days = (
            trigger_input.trigger_type == "calendar"
            and trigger_input.calendar_rule is CalendarRuleKind.BUSINESS_DAYS
        )
        if not is_business_days:
            return compute_next_run_at(trigger_input, now=now, timezone_name=timezone_name)

        cron_expression = calendar_rule_to_cron(
            CalendarRuleKind.BUSINESS_DAYS, trigger_input.calendar_config or {}
        )
        holiday_entries = await self._holidays.list_covering_year(organization_id, year=now.year)
        holiday_entries += await self._holidays.list_covering_year(
            organization_id, year=now.year + 1
        )
        holidays = self._holidays.to_dates(
            holiday_entries, year=now.year
        ) | self._holidays.to_dates(holiday_entries, year=now.year + 1)
        return next_business_run_at(cron_expression, now=now, holidays=holidays)


__all__ = ["TriggerService"]
