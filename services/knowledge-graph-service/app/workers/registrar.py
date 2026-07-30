"""Recurring-job registration against ``shared_core.scheduler``.

Maps this service's statistics rollup onto that framework's
:class:`~shared_core.scheduler.Schedule`/:class:`~shared_core.scheduler.Job`
shapes. The polling loop, distributed locking, **leader election**, and
retry machinery all live in ``packages/shared-core/scheduler`` (Prompt
026) -- the same "framework owns the loop, caller owns the job
definition" split every prior AI-IOS service established.

Leader election is the right behaviour here, unlike
``services/dashboard-service``'s per-replica refresh loop: the rollup is
a pure database write with no per-replica state, so N replicas computing
it would be N times the load for an identical result, and two concurrent
recomputes of one organization would race on the same row.

A **single** platform-wide tick is registered rather than one job per
organization: the rollup already iterates tenants internally, and N jobs
polling the same tables would be N times the load for no benefit.
"""

from __future__ import annotations

from datetime import timedelta

from shared_core.scheduler import Job, JobFn, JobType, Schedule, SchedulerManager
from shared_core.scheduler import ScheduleType as FrameworkScheduleType

STATISTICS_ROLLUP_JOB_ID = "knowledge-graph-statistics-rollup"
"""Deterministic job id, so re-registering replaces rather than leaks."""


def register_statistics_rollup(
    manager: SchedulerManager, fn: JobFn, *, interval_seconds: float
) -> Job:
    """Register the recurring statistics rollup.

    Raises:
        ValueError: If *interval_seconds* is not positive.
    """
    if interval_seconds <= 0:
        raise ValueError(f"Statistics rollup interval must be positive, got {interval_seconds!r}.")
    job = Job(
        job_id=STATISTICS_ROLLUP_JOB_ID,
        job_name=STATISTICS_ROLLUP_JOB_ID,
        job_type=JobType.SYSTEM,
        fn=fn,
        schedule=Schedule(
            schedule_type=FrameworkScheduleType.FIXED_RATE,
            interval=timedelta(seconds=interval_seconds),
        ),
        metadata={"component": "knowledge-graph-statistics"},
    )
    # The manager's return value, not the local `job`. Registration is
    # what computes the first ``next_run``, and the registry transitions
    # a *copy* -- so handing back the object built above would give the
    # caller a job that reads as never scheduled.
    return manager.register_job(job)


__all__ = ["STATISTICS_ROLLUP_JOB_ID", "register_statistics_rollup"]
