"""Recurring scheduled-report tick registration against
``shared_core.scheduler``.

Maps this service's own "run every report schedule that has come due"
work onto that framework's :class:`~shared_core.scheduler.Schedule`/
:class:`~shared_core.scheduler.Job` shapes. The polling loop,
distributed locking, **leader election**, and retry machinery all live
in ``packages/shared-core/scheduler`` (Prompt 026) -- the same
"framework owns the loop, caller owns the job definition" split
``services/alerting-service``'s own registrar established.

Leader election is what matters most here: without it, every replica
would run the same due schedule, generating duplicate reports and
mailing each recipient once per replica.

A **single** platform-wide tick is registered rather than one job per
organization. This service's due-schedule query is already scoped by
time, not tenant, so one poll serves every organization -- and N jobs
polling the same table would be N times the load for no benefit.
"""

from __future__ import annotations

from datetime import timedelta

from shared_core.scheduler import Job, JobFn, JobType, Schedule, SchedulerManager
from shared_core.scheduler import ScheduleType as FrameworkScheduleType

SCHEDULED_REPORT_JOB_ID = "reporting-scheduled-reports"
"""Deterministic job id, so re-registering replaces rather than leaks."""


def register_scheduled_report_tick(
    manager: SchedulerManager, fn: JobFn, *, interval_seconds: float
) -> Job:
    """Register the recurring due-schedule sweep.

    Raises:
        ValueError: If *interval_seconds* is not positive.
    """
    if interval_seconds <= 0:
        raise ValueError(
            f"Scheduled-report poll interval must be positive, got {interval_seconds!r}."
        )
    job = Job(
        job_id=SCHEDULED_REPORT_JOB_ID,
        job_name=SCHEDULED_REPORT_JOB_ID,
        job_type=JobType.SYSTEM,
        fn=fn,
        schedule=Schedule(
            schedule_type=FrameworkScheduleType.FIXED_RATE,
            interval=timedelta(seconds=interval_seconds),
        ),
        metadata={"component": "scheduled-reports"},
    )
    manager.register_job(job)
    return job


__all__ = ["SCHEDULED_REPORT_JOB_ID", "register_scheduled_report_tick"]
