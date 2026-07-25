"""Wires :class:`~app.models.automation_schedule.AutomationSchedule`
rows into ``shared_core.scheduler``'s own cron engine, per docs/040
"EXECUTION MODES" "Scheduled". This module only *builds* the ``Job``
objects a schedule maps to -- the running ``SchedulerManager`` itself
(heartbeat, leader election, dispatch loop) is assembled once at
process startup in ``app/core/factory.py``, the same "framework owns
the loop, caller owns the job definitions" split
``shared_core.queue``'s own ``@job``/``register_jobs`` pair already
established.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from uuid import UUID

from shared_core.scheduler.job import Job, JobType, build_job
from shared_core.scheduler.schedule import Schedule, ScheduleType

from app.models.automation_schedule import AutomationSchedule

TriggerScheduledExecution = Callable[[UUID, UUID], Awaitable[None]]
"""Called with ``(job_id, organization_id)`` when a schedule comes due."""


def build_scheduler_job(schedule: AutomationSchedule, *, trigger: TriggerScheduledExecution) -> Job:
    """Build the ``shared_core.scheduler`` ``Job`` one enabled
    :class:`AutomationSchedule` maps to.
    """
    job_id = schedule.job_id
    organization_id = schedule.organization_id

    async def _run(_job: Job) -> None:
        await trigger(job_id, organization_id)

    return build_job(
        job_name=f"automation-schedule-{schedule.id}",
        job_type=JobType.AUTOMATION,
        fn=_run,
        schedule=Schedule(
            schedule_type=ScheduleType.CRON_EXPRESSION,
            cron_expression=schedule.cron_expression,
        ),
        organization_id=str(organization_id),
        payload={"schedule_id": str(schedule.id), "job_id": str(job_id)},
    )


__all__ = ["TriggerScheduledExecution", "build_scheduler_job"]
