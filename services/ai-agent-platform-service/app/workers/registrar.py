"""Recurring-job registration against ``shared_core.scheduler``.

Maps this service's four background jobs onto that framework's
:class:`~shared_core.scheduler.Schedule`/:class:`~shared_core.scheduler.Job`
shapes. The polling loop, distributed locking, leader election, and retry
machinery all live in ``packages/shared-core/scheduler`` (Prompt 026).

**All four jobs are leader-elected.** Each is pure database (plus,
for task dispatch and checkpoint recovery, model-provider I/O) work
with no per-replica state, so N replicas would be N times the load for
an identical result -- and concurrent sweeps of the same due rows
would race.
"""

from __future__ import annotations

from datetime import timedelta

from shared_core.scheduler import Job, JobFn, JobType, Schedule, SchedulerManager
from shared_core.scheduler import ScheduleType as FrameworkScheduleType

TASK_DISPATCH_SWEEP_JOB_ID = "ai-agent-platform-task-dispatch-sweep"
CHECKPOINT_RECOVERY_SWEEP_JOB_ID = "ai-agent-platform-checkpoint-recovery-sweep"
STATISTICS_ROLLUP_JOB_ID = "ai-agent-platform-statistics-rollup"
BENCHMARK_SWEEP_JOB_ID = "ai-agent-platform-benchmark-sweep"
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


def register_task_dispatch_sweep(
    manager: SchedulerManager, fn: JobFn, *, interval_seconds: float
) -> Job:
    """Register the recurring task dispatch sweep.

    Raises:
        ValueError: If *interval_seconds* is not positive.
    """
    return _register(
        manager,
        fn,
        job_id=TASK_DISPATCH_SWEEP_JOB_ID,
        interval_seconds=interval_seconds,
        component="ai-agent-platform-task-dispatch-sweep",
    )


def register_checkpoint_recovery_sweep(
    manager: SchedulerManager, fn: JobFn, *, interval_seconds: float
) -> Job:
    """Register the recurring checkpoint recovery sweep.

    Raises:
        ValueError: If *interval_seconds* is not positive.
    """
    return _register(
        manager,
        fn,
        job_id=CHECKPOINT_RECOVERY_SWEEP_JOB_ID,
        interval_seconds=interval_seconds,
        component="ai-agent-platform-checkpoint-recovery-sweep",
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
        component="ai-agent-platform-statistics-rollup",
    )


def register_benchmark_sweep(
    manager: SchedulerManager, fn: JobFn, *, interval_seconds: float
) -> Job:
    """Register the recurring benchmark sweep.

    Raises:
        ValueError: If *interval_seconds* is not positive.
    """
    return _register(
        manager,
        fn,
        job_id=BENCHMARK_SWEEP_JOB_ID,
        interval_seconds=interval_seconds,
        component="ai-agent-platform-benchmark-sweep",
    )


__all__ = [
    "BENCHMARK_SWEEP_JOB_ID",
    "CHECKPOINT_RECOVERY_SWEEP_JOB_ID",
    "STATISTICS_ROLLUP_JOB_ID",
    "TASK_DISPATCH_SWEEP_JOB_ID",
    "register_benchmark_sweep",
    "register_checkpoint_recovery_sweep",
    "register_statistics_rollup",
    "register_task_dispatch_sweep",
]
