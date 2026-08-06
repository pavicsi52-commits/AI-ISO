"""Recurring-job registration against ``shared_core.scheduler``.

Maps this service's five background jobs onto that framework's
:class:`~shared_core.scheduler.Schedule`/:class:`~shared_core.scheduler.Job`
shapes. The polling loop, distributed locking, leader election, and retry
machinery all live in ``packages/shared-core/scheduler`` (Prompt 026).

**All five jobs are leader-elected.** Each is pure database (plus, for
the retry/replay sweeps, outbound HTTP) work with no per-replica state,
so N replicas would be N times the load for an identical result -- and
concurrent sweeps of the same due retries would race on the same rows.
"""

from __future__ import annotations

from datetime import timedelta

from shared_core.scheduler import Job, JobFn, JobType, Schedule, SchedulerManager
from shared_core.scheduler import ScheduleType as FrameworkScheduleType

RETRY_SWEEP_JOB_ID = "webhook-retry-sweep"
REPLAY_PROCESSOR_JOB_ID = "webhook-replay-processor"
STATISTICS_ROLLUP_JOB_ID = "webhook-statistics-rollup"
IDEMPOTENCY_EXPIRY_SWEEP_JOB_ID = "webhook-idempotency-expiry-sweep"
SECRET_EXPIRY_SWEEP_JOB_ID = "webhook-secret-expiry-sweep"
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


def register_retry_sweep(manager: SchedulerManager, fn: JobFn, *, interval_seconds: float) -> Job:
    """Register the recurring retry sweep.

    Raises:
        ValueError: If *interval_seconds* is not positive.
    """
    return _register(
        manager, fn, job_id=RETRY_SWEEP_JOB_ID, interval_seconds=interval_seconds,
        component="webhook-retry-sweep",
    )


def register_replay_processor(manager: SchedulerManager, fn: JobFn, *, interval_seconds: float) -> Job:
    """Register the recurring replay processor.

    Raises:
        ValueError: If *interval_seconds* is not positive.
    """
    return _register(
        manager, fn, job_id=REPLAY_PROCESSOR_JOB_ID, interval_seconds=interval_seconds,
        component="webhook-replay-processor",
    )


def register_statistics_rollup(manager: SchedulerManager, fn: JobFn, *, interval_seconds: float) -> Job:
    """Register the recurring statistics rollup.

    Raises:
        ValueError: If *interval_seconds* is not positive.
    """
    return _register(
        manager, fn, job_id=STATISTICS_ROLLUP_JOB_ID, interval_seconds=interval_seconds,
        component="webhook-statistics-rollup",
    )


def register_idempotency_expiry_sweep(
    manager: SchedulerManager, fn: JobFn, *, interval_seconds: float
) -> Job:
    """Register the recurring idempotency-key expiry sweep.

    Raises:
        ValueError: If *interval_seconds* is not positive.
    """
    return _register(
        manager, fn, job_id=IDEMPOTENCY_EXPIRY_SWEEP_JOB_ID, interval_seconds=interval_seconds,
        component="webhook-idempotency-expiry-sweep",
    )


def register_secret_expiry_sweep(
    manager: SchedulerManager, fn: JobFn, *, interval_seconds: float
) -> Job:
    """Register the recurring signing-secret expiry sweep.

    Raises:
        ValueError: If *interval_seconds* is not positive.
    """
    return _register(
        manager, fn, job_id=SECRET_EXPIRY_SWEEP_JOB_ID, interval_seconds=interval_seconds,
        component="webhook-secret-expiry-sweep",
    )


__all__ = [
    "IDEMPOTENCY_EXPIRY_SWEEP_JOB_ID",
    "REPLAY_PROCESSOR_JOB_ID",
    "RETRY_SWEEP_JOB_ID",
    "SECRET_EXPIRY_SWEEP_JOB_ID",
    "STATISTICS_ROLLUP_JOB_ID",
    "register_idempotency_expiry_sweep",
    "register_replay_processor",
    "register_retry_sweep",
    "register_secret_expiry_sweep",
    "register_statistics_rollup",
]
