"""Recurring-job registration against ``shared_core.scheduler``.

Maps this service's three background jobs onto that framework's
:class:`~shared_core.scheduler.Schedule`/:class:`~shared_core.scheduler.Job`
shapes. The polling loop, distributed locking, leader election, and retry
machinery all live in ``packages/shared-core/scheduler`` (Prompt 026).

**All three jobs are leader-elected.** Each is pure database (plus, for
the health sweep, outbound HTTP) work with no per-replica state, so N
replicas would be N times the load for an identical result -- and
concurrent sweeps of the same due quota resets would race on the same
rows.
"""

from __future__ import annotations

from datetime import timedelta

from shared_core.scheduler import Job, JobFn, JobType, Schedule, SchedulerManager
from shared_core.scheduler import ScheduleType as FrameworkScheduleType

HEALTH_PROBE_SWEEP_JOB_ID = "gateway-health-probe-sweep"
STATISTICS_ROLLUP_JOB_ID = "gateway-statistics-rollup"
QUOTA_RESET_SWEEP_JOB_ID = "gateway-quota-reset-sweep"
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
    """Register the recurring health-probe sweep.

    Raises:
        ValueError: If *interval_seconds* is not positive.
    """
    return _register(
        manager,
        fn,
        job_id=HEALTH_PROBE_SWEEP_JOB_ID,
        interval_seconds=interval_seconds,
        component="gateway-health-probe-sweep",
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
        component="gateway-statistics-rollup",
    )


def register_quota_reset_sweep(manager: SchedulerManager, fn: JobFn, *, interval_seconds: float) -> Job:
    """Register the recurring quota reset sweep.

    Raises:
        ValueError: If *interval_seconds* is not positive.
    """
    return _register(
        manager,
        fn,
        job_id=QUOTA_RESET_SWEEP_JOB_ID,
        interval_seconds=interval_seconds,
        component="gateway-quota-reset-sweep",
    )


__all__ = [
    "HEALTH_PROBE_SWEEP_JOB_ID",
    "QUOTA_RESET_SWEEP_JOB_ID",
    "STATISTICS_ROLLUP_JOB_ID",
    "register_health_probe_sweep",
    "register_quota_reset_sweep",
    "register_statistics_rollup",
]
