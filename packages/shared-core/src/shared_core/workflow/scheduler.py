"""Scheduler integration.

Per docs/028_Enterprise_Workflow_SDK.md.txt "SCHEDULER INTEGRATION":
Scheduled Workflows, Recurring Workflows, Cron Workflows, Delayed
Workflows. "Integrate with Prompt 026." Reuses
:func:`shared_core.scheduler.job.build_job`/
:class:`~shared_core.scheduler.schedule.Schedule` directly rather than
a second scheduling mechanism -- this module only builds the ``Job``
whose ``fn`` triggers one workflow execution, via a caller-supplied
async "run this workflow" callback.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from datetime import timedelta
from typing import Any

from shared_core.scheduler.job import Job, JobType, build_job
from shared_core.scheduler.schedule import Schedule, ScheduleType

WorkflowTrigger = Callable[[str], Awaitable[None]]


def build_scheduled_workflow_job(
    *,
    job_name: str,
    workflow_id: str,
    schedule: Schedule,
    trigger: WorkflowTrigger,
    **overrides: Any,
) -> Job:
    """Build a scheduler ``Job`` that triggers *workflow_id* on *schedule* ("Scheduled Workflows").

    *trigger* is called with *workflow_id* every time the job fires --
    typically :meth:`shared_core.workflow.manager.WorkflowManager.start_execution`.
    """

    async def fn(_job: Job) -> None:
        await trigger(workflow_id)

    return build_job(
        job_name=job_name, job_type=JobType.AUTOMATION, fn=fn, schedule=schedule, **overrides
    )


def cron_schedule(expression: str) -> Schedule:
    """Build a ``CRON_EXPRESSION`` schedule ("Cron Workflows")."""
    return Schedule(schedule_type=ScheduleType.CRON_EXPRESSION, cron_expression=expression)


def recurring_schedule(interval_seconds: float) -> Schedule:
    """Build a ``FIXED_RATE`` schedule ("Recurring Workflows")."""
    return Schedule(
        schedule_type=ScheduleType.FIXED_RATE, interval=timedelta(seconds=interval_seconds)
    )


def delayed_schedule(delay_seconds: float) -> Schedule:
    """Build a ``FIXED_DELAY`` schedule ("Delayed Workflows")."""
    return Schedule(schedule_type=ScheduleType.FIXED_DELAY, delay=timedelta(seconds=delay_seconds))


__all__ = [
    "WorkflowTrigger",
    "build_scheduled_workflow_job",
    "cron_schedule",
    "delayed_schedule",
    "recurring_schedule",
]
