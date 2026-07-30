"""Recurring-job registration against ``shared_core.scheduler``.

Maps this service's two background jobs onto that framework's
:class:`~shared_core.scheduler.Schedule`/:class:`~shared_core.scheduler.Job`
shapes. The polling loop, distributed locking, leader election, and retry
machinery all live in ``packages/shared-core/scheduler`` (Prompt 026).

**Both jobs are leader-elected.** Each is pure database work with no
per-replica state, so N replicas would be N times the load for an
identical result -- and two concurrent sweeps of one organization would
race on the same rows.
"""

from __future__ import annotations

from datetime import timedelta

from shared_core.scheduler import Job, JobFn, JobType, Schedule, SchedulerManager
from shared_core.scheduler import ScheduleType as FrameworkScheduleType

STATISTICS_ROLLUP_JOB_ID = "policy-engine-statistics-rollup"
"""Deterministic job id, so re-registering replaces rather than leaks."""

APPROVAL_SWEEP_JOB_ID = "policy-engine-approval-sweep"
"""Deterministic job id for the approval and quota sweep."""


def _register(
    manager: SchedulerManager,
    fn: JobFn,
    *,
    job_id: str,
    interval_seconds: float,
    component: str,
) -> Job:
    """Register one fixed-rate system job.

    Raises:
        ValueError: If *interval_seconds* is not positive. Zero would
            busy-loop the scheduler; negative is meaningless.
    """
    if interval_seconds <= 0:
        raise ValueError(f"The {component} interval must be positive, got {interval_seconds!r}.")
    job = Job(
        job_id=job_id,
        job_name=job_id,
        job_type=JobType.SYSTEM,
        fn=fn,
        schedule=Schedule(
            schedule_type=FrameworkScheduleType.FIXED_RATE,
            interval=timedelta(seconds=interval_seconds),
        ),
        metadata={"component": component},
    )
    # The manager's return value, not the local `job`: registration is
    # what computes the first due time, and the registry transitions a
    # copy -- so returning the object built above would hand the caller a
    # job that reads as never scheduled.
    return manager.register_job(job)


def register_statistics_rollup(
    manager: SchedulerManager, fn: JobFn, *, interval_seconds: float
) -> Job:
    """Register the recurring analytics rollup.

    Raises:
        ValueError: If *interval_seconds* is not positive.
    """
    return _register(
        manager,
        fn,
        job_id=STATISTICS_ROLLUP_JOB_ID,
        interval_seconds=interval_seconds,
        component="policy-engine-statistics",
    )


def register_approval_sweep(
    manager: SchedulerManager, fn: JobFn, *, interval_seconds: float
) -> Job:
    """Register the approval-expiry and quota-period sweep.

    A separate job from the rollup, on a shorter interval, because an
    expired approval sitting in a pending queue is an actionable item on
    somebody's list that can never complete -- and a queue full of those
    stops being read at all.

    Raises:
        ValueError: If *interval_seconds* is not positive.
    """
    return _register(
        manager,
        fn,
        job_id=APPROVAL_SWEEP_JOB_ID,
        interval_seconds=interval_seconds,
        component="policy-engine-maintenance",
    )


__all__ = [
    "APPROVAL_SWEEP_JOB_ID",
    "STATISTICS_ROLLUP_JOB_ID",
    "register_approval_sweep",
    "register_statistics_rollup",
]
