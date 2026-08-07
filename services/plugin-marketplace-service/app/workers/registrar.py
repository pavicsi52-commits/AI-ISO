"""Recurring-job registration against ``shared_core.scheduler``.

Maps this service's four background jobs onto that framework's
:class:`~shared_core.scheduler.Schedule`/:class:`~shared_core.scheduler.Job`
shapes. The polling loop, distributed locking, leader election, and retry
machinery all live in ``packages/shared-core/scheduler`` (Prompt 026).

**All four jobs are leader-elected.** Each is pure database (plus, for
the health probe, outbound HTTP) work with no per-replica state, so N
replicas would be N times the load for an identical result -- and
concurrent sweeps of the same due rows would race.
"""

from __future__ import annotations

from datetime import timedelta

from shared_core.scheduler import Job, JobFn, JobType, Schedule, SchedulerManager
from shared_core.scheduler import ScheduleType as FrameworkScheduleType

HEALTH_PROBE_SWEEP_JOB_ID = "plugin-marketplace-health-probe-sweep"
MARKETPLACE_APPROVAL_SWEEP_JOB_ID = "plugin-marketplace-approval-sweep"
STATISTICS_ROLLUP_JOB_ID = "plugin-marketplace-statistics-rollup"
REVIEW_MODERATION_SWEEP_JOB_ID = "plugin-marketplace-review-moderation-sweep"
"""Deterministic job ids, so re-registering replaces rather than leaks."""


def _register(
    manager: SchedulerManager, fn: JobFn, *, job_id: str, interval_seconds: float, component: str
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


def register_health_probe_sweep(
    manager: SchedulerManager, fn: JobFn, *, interval_seconds: float
) -> Job:
    """Register the recurring plugin health-probe sweep.

    Raises:
        ValueError: If *interval_seconds* is not positive.
    """
    return _register(
        manager,
        fn,
        job_id=HEALTH_PROBE_SWEEP_JOB_ID,
        interval_seconds=interval_seconds,
        component="plugin-marketplace-health-probe-sweep",
    )


def register_marketplace_approval_sweep(
    manager: SchedulerManager, fn: JobFn, *, interval_seconds: float
) -> Job:
    """Register the recurring marketplace-approval sweep.

    Raises:
        ValueError: If *interval_seconds* is not positive.
    """
    return _register(
        manager,
        fn,
        job_id=MARKETPLACE_APPROVAL_SWEEP_JOB_ID,
        interval_seconds=interval_seconds,
        component="plugin-marketplace-approval-sweep",
    )


def register_statistics_rollup(
    manager: SchedulerManager, fn: JobFn, *, interval_seconds: float
) -> Job:
    """Register the recurring statistics rollup.

    Raises:
        ValueError: If *interval_seconds* is not positive.
    """
    return _register(
        manager,
        fn,
        job_id=STATISTICS_ROLLUP_JOB_ID,
        interval_seconds=interval_seconds,
        component="plugin-marketplace-statistics-rollup",
    )


def register_review_moderation_sweep(
    manager: SchedulerManager, fn: JobFn, *, interval_seconds: float
) -> Job:
    """Register the recurring review moderation sweep.

    Raises:
        ValueError: If *interval_seconds* is not positive.
    """
    return _register(
        manager,
        fn,
        job_id=REVIEW_MODERATION_SWEEP_JOB_ID,
        interval_seconds=interval_seconds,
        component="plugin-marketplace-review-moderation-sweep",
    )


__all__ = [
    "HEALTH_PROBE_SWEEP_JOB_ID",
    "MARKETPLACE_APPROVAL_SWEEP_JOB_ID",
    "REVIEW_MODERATION_SWEEP_JOB_ID",
    "STATISTICS_ROLLUP_JOB_ID",
    "register_health_probe_sweep",
    "register_marketplace_approval_sweep",
    "register_review_moderation_sweep",
    "register_statistics_rollup",
]
