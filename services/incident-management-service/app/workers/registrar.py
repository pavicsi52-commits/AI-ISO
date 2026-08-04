"""Recurring-job registration against ``shared_core.scheduler``.

Maps this service's four background jobs onto that framework's
:class:`~shared_core.scheduler.Schedule`/:class:`~shared_core.scheduler.Job`
shapes. The polling loop, distributed locking, leader election, and retry
machinery all live in ``packages/shared-core/scheduler`` (Prompt 026).

**All four jobs are leader-elected.** Each is pure database work with no
per-replica state, so N replicas would be N times the load for an
identical result -- and concurrent sweeps of one organization's SLA
clocks or escalation ladder would race on the same rows, double-firing
an escalation or double-recording a breach.
"""

from __future__ import annotations

from datetime import timedelta

from shared_core.scheduler import Job, JobFn, JobType, Schedule, SchedulerManager
from shared_core.scheduler import ScheduleType as FrameworkScheduleType

SLA_SWEEP_JOB_ID = "incident-sla-sweep"
ESCALATION_SWEEP_JOB_ID = "incident-escalation-sweep"
STATISTICS_ROLLUP_JOB_ID = "incident-statistics-rollup"
MAINTENANCE_SWEEP_JOB_ID = "incident-maintenance-sweep"
"""Deterministic job ids, so re-registering replaces rather than leaks."""


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


def register_sla_sweep(manager: SchedulerManager, fn: JobFn, *, interval_seconds: float) -> Job:
    """Register the recurring SLA clock sweep.

    Raises:
        ValueError: If *interval_seconds* is not positive.
    """
    return _register(
        manager,
        fn,
        job_id=SLA_SWEEP_JOB_ID,
        interval_seconds=interval_seconds,
        component="incident-sla-sweep",
    )


def register_escalation_sweep(
    manager: SchedulerManager, fn: JobFn, *, interval_seconds: float
) -> Job:
    """Register the recurring escalation ladder sweep.

    Raises:
        ValueError: If *interval_seconds* is not positive.
    """
    return _register(
        manager,
        fn,
        job_id=ESCALATION_SWEEP_JOB_ID,
        interval_seconds=interval_seconds,
        component="incident-escalation-sweep",
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
        component="incident-statistics",
    )


def register_maintenance_sweep(
    manager: SchedulerManager, fn: JobFn, *, interval_seconds: float
) -> Job:
    """Register the recurring maintenance sweep.

    Raises:
        ValueError: If *interval_seconds* is not positive.
    """
    return _register(
        manager,
        fn,
        job_id=MAINTENANCE_SWEEP_JOB_ID,
        interval_seconds=interval_seconds,
        component="incident-maintenance",
    )


__all__ = [
    "ESCALATION_SWEEP_JOB_ID",
    "MAINTENANCE_SWEEP_JOB_ID",
    "SLA_SWEEP_JOB_ID",
    "STATISTICS_ROLLUP_JOB_ID",
    "register_escalation_sweep",
    "register_maintenance_sweep",
    "register_sla_sweep",
    "register_statistics_rollup",
]
