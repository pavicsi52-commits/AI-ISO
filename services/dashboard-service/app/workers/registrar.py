"""Recurring-job registration against ``shared_core.scheduler``.

Maps this service's analytics rollup onto that framework's
:class:`~shared_core.scheduler.Schedule`/:class:`~shared_core.scheduler.Job`
shapes. The polling loop, distributed locking, **leader election**, and
retry machinery all live in ``packages/shared-core/scheduler`` (Prompt
026) -- the same "framework owns the loop, caller owns the job
definition" split ``services/reporting-service`` established.

Only the rollup is registered here. The live-refresh loop deliberately
does **not** go through the scheduler, because leader election is
exactly the wrong behaviour for it: subscribers are per-process, so one
elected replica would refresh only its own watchers. See
:mod:`app.workers.refresh`.

A **single** platform-wide tick is registered rather than one job per
organization: the rollup already iterates tenants internally, and N
jobs polling the same tables would be N times the load for no benefit.
"""

from __future__ import annotations

from datetime import timedelta

from shared_core.scheduler import Job, JobFn, JobType, Schedule, SchedulerManager
from shared_core.scheduler import ScheduleType as FrameworkScheduleType

STATISTICS_ROLLUP_JOB_ID = "dashboard-statistics-rollup"
"""Deterministic job id, so re-registering replaces rather than leaks."""


def register_statistics_rollup(
    manager: SchedulerManager, fn: JobFn, *, interval_seconds: float
) -> Job:
    """Register the recurring analytics rollup.

    Raises:
        ValueError: If *interval_seconds* is not positive.
    """
    if interval_seconds <= 0:
        raise ValueError(f"Analytics rollup interval must be positive, got {interval_seconds!r}.")
    job = Job(
        job_id=STATISTICS_ROLLUP_JOB_ID,
        job_name=STATISTICS_ROLLUP_JOB_ID,
        job_type=JobType.SYSTEM,
        fn=fn,
        schedule=Schedule(
            schedule_type=FrameworkScheduleType.FIXED_RATE,
            interval=timedelta(seconds=interval_seconds),
        ),
        metadata={"component": "dashboard-analytics"},
    )
    manager.register_job(job)
    return job


__all__ = ["STATISTICS_ROLLUP_JOB_ID", "register_statistics_rollup"]
