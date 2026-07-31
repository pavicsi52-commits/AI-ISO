"""Recurring-job registration against ``shared_core.scheduler``.

Maps this service's two background jobs onto that framework's
:class:`~shared_core.scheduler.Schedule`/:class:`~shared_core.scheduler.Job`
shapes. The polling loop, distributed locking, leader election, and retry
machinery all live in ``packages/shared-core/scheduler`` (Prompt 026).

**Both jobs are leader-elected.** Each is pure database work with no
per-replica state, so N replicas would be N times the load for an
identical result -- and two concurrent sweeps of one organization would
race on the same exception rows, which for an expiry sweep means an
exception expired twice and counted twice in the statistics that follow.
"""

from __future__ import annotations

from datetime import timedelta

from shared_core.scheduler import Job, JobFn, JobType, Schedule, SchedulerManager
from shared_core.scheduler import ScheduleType as FrameworkScheduleType

SCORING_ROLLUP_JOB_ID = "compliance-scoring-rollup"
"""Deterministic job id, so re-registering replaces rather than leaks."""

EXCEPTION_SWEEP_JOB_ID = "compliance-exception-sweep"
"""Deterministic job id for the exception-expiry and assessment-reap sweep."""


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


def register_scoring_rollup(
    manager: SchedulerManager, fn: JobFn, *, interval_seconds: float
) -> Job:
    """Register the recurring statistics rollup.

    Raises:
        ValueError: If *interval_seconds* is not positive.
    """
    return _register(
        manager,
        fn,
        job_id=SCORING_ROLLUP_JOB_ID,
        interval_seconds=interval_seconds,
        component="compliance-statistics",
    )


def register_exception_sweep(
    manager: SchedulerManager, fn: JobFn, *, interval_seconds: float
) -> Job:
    """Register the exception-expiry and stuck-assessment sweep.

    A separate job from the rollup because the two failures it prevents
    are both silent. A lapsed exception that is never marked EXPIRED goes
    on waiving a control it no longer covers; a RUNNING assessment left
    by a dead worker blocks the next scheduled run for its framework, and
    the symptom of *that* is nothing happening at all.

    Raises:
        ValueError: If *interval_seconds* is not positive.
    """
    return _register(
        manager,
        fn,
        job_id=EXCEPTION_SWEEP_JOB_ID,
        interval_seconds=interval_seconds,
        component="compliance-maintenance",
    )


__all__ = [
    "EXCEPTION_SWEEP_JOB_ID",
    "SCORING_ROLLUP_JOB_ID",
    "register_exception_sweep",
    "register_scoring_rollup",
]
