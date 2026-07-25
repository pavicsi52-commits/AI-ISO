"""Discovery schedule registration against ``shared_core.scheduler``.

Per docs/037 "SCHEDULING": "Integrate with Prompt 026." This module
only *maps* a :class:`~app.models.discovery_schedule.DiscoverySchedule`
row onto that framework's own :class:`~shared_core.scheduler.Schedule`/
:class:`~shared_core.scheduler.Job` shapes and registers it -- the
actual cron/interval computation, distributed locking, leader
election, and retry machinery all live in
``packages/shared-core/scheduler`` (already built and tested in Prompt
026) and are not reimplemented here.
"""

from __future__ import annotations

from datetime import timedelta

from shared_core.enums.priority import Priority
from shared_core.scheduler import Job, JobFn, JobType, Schedule, SchedulerManager
from shared_core.scheduler import ScheduleType as FrameworkScheduleType

from app.models.discovery_schedule import DiscoverySchedule
from app.models.enums import ScheduleType

_PRIORITY_THRESHOLDS: tuple[tuple[int, Priority], ...] = (
    (1, Priority.BACKGROUND),
    (3, Priority.LOW),
    (6, Priority.NORMAL),
    (8, Priority.HIGH),
)
"""Maps :attr:`DiscoverySchedule.priority`'s 0-10 integer scale onto the
scheduler framework's own 5-level :class:`~shared_core.enums.priority
.Priority` -- the two scales don't share a representation, so this is a
deliberate, documented projection, not a lossless conversion.
"""


def _framework_priority(priority: int) -> Priority:
    """Project a 0-10 :attr:`DiscoverySchedule.priority` onto :class:`Priority`."""
    for threshold, level in _PRIORITY_THRESHOLDS:
        if priority <= threshold:
            return level
    return Priority.CRITICAL


def build_schedule(discovery_schedule: DiscoverySchedule) -> Schedule:
    """Map a :class:`DiscoverySchedule` row onto the scheduler
    framework's own :class:`~shared_core.scheduler.Schedule`.

    Raises:
        ValueError: If *discovery_schedule* is a ``CRON``/``INTERVAL``
            schedule missing the field that type requires.
    """
    if discovery_schedule.schedule_type == ScheduleType.ONE_TIME:
        if discovery_schedule.next_run_at is None:
            raise ValueError("A ONE_TIME schedule requires next_run_at.")
        return Schedule(
            schedule_type=FrameworkScheduleType.SCHEDULED_TIME,
            run_at=discovery_schedule.next_run_at,
        )
    if discovery_schedule.schedule_type == ScheduleType.CRON:
        if not discovery_schedule.cron_expression:
            raise ValueError("A CRON schedule requires cron_expression.")
        return Schedule(
            schedule_type=FrameworkScheduleType.CRON_EXPRESSION,
            cron_expression=discovery_schedule.cron_expression,
        )
    if discovery_schedule.schedule_type in (ScheduleType.INTERVAL, ScheduleType.RECURRING):
        if discovery_schedule.cron_expression:
            return Schedule(
                schedule_type=FrameworkScheduleType.CRON_EXPRESSION,
                cron_expression=discovery_schedule.cron_expression,
            )
        if discovery_schedule.interval_seconds is None:
            raise ValueError(
                "An INTERVAL/RECURRING schedule requires interval_seconds or cron_expression."
            )
        return Schedule(
            schedule_type=FrameworkScheduleType.FIXED_RATE,
            interval=timedelta(seconds=discovery_schedule.interval_seconds),
        )
    raise ValueError(f"Unsupported schedule type: {discovery_schedule.schedule_type}")


def register_schedule(
    manager: SchedulerManager, discovery_schedule: DiscoverySchedule, fn: JobFn
) -> Job:
    """Register *discovery_schedule* with *manager*, returning the
    framework :class:`~shared_core.scheduler.Job` it built.

    Uses ``str(discovery_schedule.id)`` as the framework job's own
    ``job_id`` (rather than :func:`~shared_core.scheduler.build_job`'s
    freshly-random one) so that re-registering the same
    :class:`DiscoverySchedule` -- on every ``PUT /discovery/schedules
    /{id}`` -- replaces its prior registration in place
    (:meth:`~shared_core.scheduler.registry.JobRegistry.register` is a
    plain ``dict[job_id] = job`` upsert) instead of leaking a second,
    orphaned one, and so ``DELETE /discovery/schedules/{id}`` can cancel
    the exact same registration by id without this module needing to
    persist a separate id mapping anywhere.
    """
    job = Job(
        job_id=str(discovery_schedule.id),
        job_name=f"discovery-schedule-{discovery_schedule.id}",
        job_type=JobType.BACKGROUND,
        fn=fn,
        schedule=build_schedule(discovery_schedule),
        organization_id=str(discovery_schedule.organization_id),
        priority=_framework_priority(discovery_schedule.priority),
        metadata={
            "discovery_schedule_id": str(discovery_schedule.id),
            "profile_id": str(discovery_schedule.profile_id),
            "concurrency_limit": discovery_schedule.concurrency_limit,
        },
    )
    manager.register_job(job)
    return job


__all__ = ["build_schedule", "register_schedule"]
