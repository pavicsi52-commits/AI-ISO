"""Recurring escalation-pass registration against
``shared_core.scheduler``.

Maps this service's own "advance escalations for an organization"
work onto that framework's own :class:`~shared_core.scheduler.Schedule`/
:class:`~shared_core.scheduler.Job` shapes -- the cron computation,
distributed locking, leader election, and retry machinery all live in
``packages/shared-core/scheduler`` (Prompt 026), the same "framework
owns the loop, caller owns the job definitions" split
``services/monitoring-service``'s own registrar already established.

Uses ``JobType.SYSTEM`` (that enum has no ``ALERTING`` member; this is
platform housekeeping rather than a user-submitted job) and a
``FIXED_RATE`` schedule at the configured poll interval.
"""

from __future__ import annotations

from datetime import timedelta
from uuid import UUID

from shared_core.scheduler import Job, JobFn, JobType, Schedule, SchedulerManager
from shared_core.scheduler import ScheduleType as FrameworkScheduleType


def register_escalation_pass(
    manager: SchedulerManager,
    organization_id: UUID,
    fn: JobFn,
    *,
    interval_seconds: float,
) -> Job:
    """Register *organization_id*'s own recurring escalation pass.

    Uses a deterministic ``job_id`` derived from the organization so
    re-registering replaces the prior registration in place instead of
    leaking a second, orphaned one.

    Raises:
        ValueError: If *interval_seconds* is not positive.
    """
    if interval_seconds <= 0:
        raise ValueError(f"Escalation pass interval must be positive, got {interval_seconds!r}.")
    job = Job(
        job_id=f"alert-escalation-{organization_id}",
        job_name=f"alert-escalation-{organization_id}",
        job_type=JobType.SYSTEM,
        fn=fn,
        schedule=Schedule(
            schedule_type=FrameworkScheduleType.FIXED_RATE,
            interval=timedelta(seconds=interval_seconds),
        ),
        organization_id=str(organization_id),
        metadata={"organization_id": str(organization_id)},
    )
    manager.register_job(job)
    return job


__all__ = ["register_escalation_pass"]
