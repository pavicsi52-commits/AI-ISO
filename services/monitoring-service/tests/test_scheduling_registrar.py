"""Tests for :func:`app.scheduling.registrar.register_collector`/
:func:`register_synthetic_test` against a real
:class:`~shared_core.scheduler.SchedulerManager` (real Redis, real
RabbitMQ) -- no in-memory fake, matching this repository's own
``real_queue_framework``/``real_redis_client`` precedent.
"""

from __future__ import annotations

import uuid

from redis.asyncio import Redis
from shared_core.queue.factory import QueueFramework
from shared_core.scheduler import Job, JobType, create_scheduler_framework

from app.models.enums import SyntheticCheckType
from app.models.monitoring_collector import MonitoringCollector
from app.models.monitoring_synthetic_test import MonitoringSyntheticTest
from app.scheduling.registrar import register_collector, register_synthetic_test


def _collector() -> MonitoringCollector:
    return MonitoringCollector(
        id=uuid.uuid4(),
        organization_id=uuid.uuid4(),
        name="test-collector",
        collector_key="connectivity",
        interval_seconds=45.0,
    )


def _synthetic_test() -> MonitoringSyntheticTest:
    return MonitoringSyntheticTest(
        id=uuid.uuid4(),
        organization_id=uuid.uuid4(),
        check_type=SyntheticCheckType.HTTP,
        name="ping-check",
        interval_seconds=120.0,
    )


async def _noop_job(job: Job) -> None:
    return None


class TestRegisterCollector:
    async def test_registers_job_with_scheduler_manager(
        self, real_redis_client: Redis, real_queue_framework: QueueFramework
    ) -> None:
        manager = create_scheduler_framework(
            real_queue_framework.manager, real_redis_client, queue_name="test.scheduler.monitoring"
        )
        collector = _collector()

        job = register_collector(manager, collector, _noop_job)

        assert job.job_id == f"collector-{collector.id}"
        assert job.job_type == JobType.MONITORING
        assert job.schedule.interval is not None
        assert job.schedule.interval.total_seconds() == 45.0
        assert job.metadata["collector_id"] == str(collector.id)


class TestRegisterSyntheticTest:
    async def test_registers_job_with_scheduler_manager(
        self, real_redis_client: Redis, real_queue_framework: QueueFramework
    ) -> None:
        manager = create_scheduler_framework(
            real_queue_framework.manager, real_redis_client, queue_name="test.scheduler.monitoring"
        )
        test = _synthetic_test()

        job = register_synthetic_test(manager, test, _noop_job)

        assert job.job_id == f"synthetic-{test.id}"
        assert job.job_type == JobType.MONITORING
        assert job.schedule.interval is not None
        assert job.schedule.interval.total_seconds() == 120.0
        assert job.metadata["synthetic_test_id"] == str(test.id)


__all__: list[str] = []
