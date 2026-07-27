"""Tests for :func:`app.scheduling.registrar.register_timer` against a
real :class:`~shared_core.scheduler.SchedulerManager` (real Redis, real
RabbitMQ) -- no in-memory fake, matching this repository's own
``real_queue_framework``/``real_redis_client`` precedent.
"""

from __future__ import annotations

import uuid

import pytest
from redis.asyncio import Redis
from shared_core.queue.factory import QueueFramework
from shared_core.scheduler import Job, JobType, create_scheduler_framework

from app.models.enums import TimerType
from app.models.workflow_timer import WorkflowTimer
from app.scheduling.registrar import register_timer


def _timer(*, cron_expression: str | None = "0 0 * * *") -> WorkflowTimer:
    return WorkflowTimer(
        organization_id=uuid.uuid4(),
        definition_id=uuid.uuid4(),
        timer_type=TimerType.CRON,
        cron_expression=cron_expression,
        recurring=True,
    )


async def _noop_job(job: Job) -> None:
    return None


class TestRegisterTimer:
    async def test_registers_job_with_scheduler_manager(
        self, real_redis_client: Redis, real_queue_framework: QueueFramework
    ) -> None:
        manager = create_scheduler_framework(
            real_queue_framework.manager, real_redis_client, queue_name="test.scheduler.due-jobs"
        )
        timer = _timer()

        job = register_timer(manager, timer, _noop_job)

        assert job.job_id == str(timer.id)
        assert job.job_type == JobType.WORKFLOW_TIMER
        assert job.schedule.cron_expression == "0 0 * * *"
        assert job.metadata["definition_id"] == str(timer.definition_id)

    async def test_missing_cron_expression_raises(
        self, real_redis_client: Redis, real_queue_framework: QueueFramework
    ) -> None:
        manager = create_scheduler_framework(
            real_queue_framework.manager, real_redis_client, queue_name="test.scheduler.due-jobs"
        )
        timer = _timer(cron_expression=None)

        with pytest.raises(ValueError, match="cron_expression"):
            register_timer(manager, timer, _noop_job)


__all__: list[str] = []
