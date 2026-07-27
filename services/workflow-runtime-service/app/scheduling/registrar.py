"""Cron/recurring workflow timer registration against
``shared_core.scheduler``.

Per docs/042 "TIMERS" "Support": Cron, Recurring Timers, Scheduled
Resume. This module only *maps* a
:class:`~app.models.workflow_timer.WorkflowTimer` row (``CRON``/
``RECURRING`` type) onto that framework's own
:class:`~shared_core.scheduler.Schedule`/:class:`~shared_core.scheduler.Job`
shapes and registers it -- the actual cron computation, distributed
locking, leader election, and retry machinery all live in
``packages/shared-core/scheduler`` (Prompt 026), the same
"framework owns the loop, caller owns the job definitions" split
``services/discovery-service``'s own ``app/scheduling/registrar.py``
already established for an analogous timer-to-schedule mapping.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from uuid import UUID

from shared_core.scheduler import Job, JobFn, JobType, Schedule, SchedulerManager
from shared_core.scheduler import ScheduleType as FrameworkScheduleType

from app.models.workflow_timer import WorkflowTimer

TriggerScheduledWorkflow = Callable[[UUID, UUID], Awaitable[None]]
"""Called with ``(definition_id, organization_id)`` when a timer comes due."""


def register_timer(manager: SchedulerManager, timer: WorkflowTimer, fn: JobFn) -> Job:
    """Register *timer* with *manager*, returning the framework
    :class:`~shared_core.scheduler.Job` it built.

    Uses ``str(timer.id)`` as the framework job's own ``job_id`` (rather
    than a freshly-random one) so that re-registering the same
    :class:`WorkflowTimer` replaces its prior registration in place
    instead of leaking a second, orphaned one.

    Raises:
        ValueError: If *timer* is a ``CRON`` timer with no
            ``cron_expression``.
    """
    if not timer.cron_expression:
        raise ValueError(f"Workflow timer {timer.id!r} has no cron_expression to schedule with.")
    job = Job(
        job_id=str(timer.id),
        job_name=f"workflow-timer-{timer.id}",
        job_type=JobType.WORKFLOW_TIMER,
        fn=fn,
        schedule=Schedule(
            schedule_type=FrameworkScheduleType.CRON_EXPRESSION,
            cron_expression=timer.cron_expression,
        ),
        organization_id=str(timer.organization_id),
        metadata={"timer_id": str(timer.id), "definition_id": str(timer.definition_id)},
    )
    manager.register_job(job)
    return job


__all__ = ["TriggerScheduledWorkflow", "register_timer"]
