"""Scheduler engine.

Per docs/026_Enterprise_Scheduler_Framework.md.txt "ACCEPTANCE
CRITERIA": Scheduler Engine. Ties :mod:`~shared_core.scheduler.schedule`,
:mod:`~shared_core.scheduler.cron`, :mod:`~shared_core.scheduler.calendar`,
and :mod:`~shared_core.scheduler.timezone` together into two operations:
computing a job's next due time, and deciding which registered jobs are
currently due. Consults :mod:`~shared_core.scheduler.dependency` so a
job with unsatisfied dependencies is never reported due, however stale
its ``next_run``.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime, timedelta

from shared_core.enums.job_status import JobStatus
from shared_core.scheduler.calendar import parse_calendar_rule
from shared_core.scheduler.cron import next_run_time
from shared_core.scheduler.dependency import DependencyGraph
from shared_core.scheduler.exceptions import InvalidScheduleError
from shared_core.scheduler.job import Job
from shared_core.scheduler.registry import JobRegistry
from shared_core.scheduler.schedule import Schedule, ScheduleType
from shared_core.scheduler.timezone import convert_timezone

_CALENDAR_SEARCH_LIMIT_MINUTES = 7 * 24 * 60

_NextRunHandler = Callable[[Schedule, datetime, str, datetime | None], datetime | None]


def _next_calendar_occurrence(rule_text: str, moment: datetime, timezone_name: str) -> datetime:
    rule = parse_calendar_rule(rule_text)
    candidate = convert_timezone(moment, to=timezone_name)
    for _ in range(_CALENDAR_SEARCH_LIMIT_MINUTES):
        if rule.is_active(candidate):
            return candidate.astimezone(UTC)
        candidate += timedelta(minutes=1)
    raise InvalidScheduleError(f"Calendar rule {rule_text!r} never becomes active within a week.")


def _handle_immediate(
    _schedule: Schedule, moment: datetime, _timezone_name: str, last_run: datetime | None
) -> datetime | None:
    return None if last_run is not None else moment


def _handle_scheduled_time(
    schedule: Schedule, _moment: datetime, _timezone_name: str, last_run: datetime | None
) -> datetime | None:
    if schedule.run_at is None:
        raise InvalidScheduleError("SCHEDULED_TIME requires 'run_at'.")
    return None if last_run is not None else schedule.run_at


def _handle_cron(
    schedule: Schedule, moment: datetime, _timezone_name: str, _last_run: datetime | None
) -> datetime | None:
    if schedule.cron_expression is None:
        raise InvalidScheduleError("CRON_EXPRESSION requires 'cron_expression'.")
    return next_run_time(schedule.cron_expression, now=moment)


def _handle_fixed_delay(
    schedule: Schedule, moment: datetime, _timezone_name: str, last_run: datetime | None
) -> datetime | None:
    if schedule.delay is None:
        raise InvalidScheduleError("FIXED_DELAY requires 'delay'.")
    return (last_run or moment) + schedule.delay


def _handle_fixed_rate(
    schedule: Schedule, moment: datetime, _timezone_name: str, last_run: datetime | None
) -> datetime | None:
    if schedule.interval is None:
        raise InvalidScheduleError("FIXED_RATE requires 'interval'.")
    candidate = (last_run or moment) + schedule.interval
    return candidate if candidate > moment else moment


def _handle_calendar(
    schedule: Schedule, moment: datetime, timezone_name: str, last_run: datetime | None
) -> datetime | None:
    if schedule.calendar_rule is None:
        return None if last_run is not None else moment
    return _next_calendar_occurrence(schedule.calendar_rule, moment, timezone_name)


def _handle_event_triggered(
    _schedule: Schedule, _moment: datetime, _timezone_name: str, _last_run: datetime | None
) -> datetime | None:
    return None


_HANDLERS: dict[ScheduleType, _NextRunHandler] = {
    ScheduleType.IMMEDIATE: _handle_immediate,
    ScheduleType.SCHEDULED_TIME: _handle_scheduled_time,
    ScheduleType.CRON_EXPRESSION: _handle_cron,
    ScheduleType.FIXED_DELAY: _handle_fixed_delay,
    ScheduleType.FIXED_RATE: _handle_fixed_rate,
    ScheduleType.CALENDAR_SCHEDULE: _handle_calendar,
    ScheduleType.BUSINESS_HOURS: _handle_calendar,
    ScheduleType.MAINTENANCE_WINDOW: _handle_calendar,
    ScheduleType.EVENT_TRIGGERED: _handle_event_triggered,
}


def compute_next_run(
    schedule: Schedule,
    *,
    now: datetime | None = None,
    timezone_name: str = "UTC",
    last_run: datetime | None = None,
) -> datetime | None:
    """Compute a job's next due time in UTC, or ``None`` if it has none left to run.

    *last_run* is this job's most recent completion time, if any --
    ``FIXED_DELAY``/``FIXED_RATE`` measure from it. *now* must be
    timezone-aware.

    Raises:
        InvalidScheduleError: If a required schedule field is missing
            (defensive; :class:`~shared_core.scheduler.schedule.Schedule`
            already validates this at construction) or a calendar rule
            never becomes active within a week.
    """
    moment = now or datetime.now(UTC)
    handler = _HANDLERS[schedule.schedule_type]
    return handler(schedule, moment, timezone_name, last_run)


class SchedulerEngine:
    """Computes due jobs and advances each job's ``next_run`` after it fires."""

    def __init__(self, registry: JobRegistry, dependencies: DependencyGraph | None = None) -> None:
        self._registry = registry
        self._dependencies = dependencies if dependencies is not None else DependencyGraph()

    def schedule_initial_run(self, job_id: str, *, now: datetime | None = None) -> Job:
        """Compute and store a freshly-registered job's first ``next_run``."""
        job = self._registry.get(job_id)
        next_run = compute_next_run(job.schedule, now=now, timezone_name=job.timezone)
        return self._registry.transition(job_id, JobStatus.SCHEDULED, next_run=next_run)

    def due_jobs(self, *, now: datetime | None = None) -> list[Job]:
        """Every scheduled job whose ``next_run`` has arrived and whose dependencies are met."""
        moment = now or datetime.now(UTC)
        due: list[Job] = []
        for job in self._registry.list_jobs():
            if job.status not in (JobStatus.SCHEDULED, JobStatus.RETRYING):
                continue
            if job.next_run is None or job.next_run > moment:
                continue
            if not self._dependencies.is_satisfied(job.job_id, self._registry.status_of):
                continue
            due.append(job)
        return due

    def advance(self, job_id: str, *, completed_at: datetime | None = None) -> Job:
        """Recompute and store a job's next ``next_run`` after it finishes running.

        A job whose schedule has nothing left to run (its
        :func:`compute_next_run` returns ``None``) is transitioned to
        ``COMPLETED`` here; anything with a next run is transitioned back
        to ``SCHEDULED``.
        """
        job = self._registry.get(job_id)
        finished_at = completed_at or datetime.now(UTC)
        next_run = compute_next_run(
            job.schedule, now=finished_at, timezone_name=job.timezone, last_run=finished_at
        )
        if next_run is None:
            return self._registry.transition(
                job_id, JobStatus.COMPLETED, last_run=finished_at, next_run=None
            )
        return self._registry.transition(
            job_id, JobStatus.SCHEDULED, last_run=finished_at, next_run=next_run
        )


__all__ = ["SchedulerEngine", "compute_next_run"]
