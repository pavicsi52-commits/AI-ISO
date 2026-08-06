"""Job registration against a real scheduler.

Against real RabbitMQ and Redis rather than a stand-in, because the
thing worth proving is that this service's job definitions are ones the
framework actually accepts -- and only the framework can decide that.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from datetime import timedelta

import pytest
import pytest_asyncio
from shared_core.cache.factory import create_cache_framework
from shared_core.cache.settings import CacheSettings
from shared_core.queue.factory import create_queue_framework
from shared_core.scheduler import Job, JobType, SchedulerManager
from shared_core.scheduler import ScheduleType as FrameworkScheduleType
from shared_core.scheduler.factory import create_scheduler_framework

from app.workers.registrar import (
    IDEMPOTENCY_EXPIRY_SWEEP_JOB_ID,
    REPLAY_PROCESSOR_JOB_ID,
    RETRY_SWEEP_JOB_ID,
    SECRET_EXPIRY_SWEEP_JOB_ID,
    STATISTICS_ROLLUP_JOB_ID,
    register_idempotency_expiry_sweep,
    register_replay_processor,
    register_retry_sweep,
    register_secret_expiry_sweep,
    register_statistics_rollup,
)
from tests.conftest import rabbitmq_test_settings, redis_test_settings

pytestmark = pytest.mark.asyncio


async def _noop(_job: Job) -> None:
    """A job body that does nothing, for registration tests."""


@pytest_asyncio.fixture
async def scheduler() -> AsyncIterator[SchedulerManager]:
    """A real scheduler manager, built the way the factory builds it."""
    queue = await create_queue_framework(rabbitmq_test_settings())
    cache = await create_cache_framework(CacheSettings(redis=redis_test_settings()))
    manager = create_scheduler_framework(
        queue.manager, cache.client, queue_name="webhook_service_test_queue"
    )
    yield manager
    await cache.shutdown()
    await queue.shutdown()


class TestJobRegistration:
    async def test_all_five_jobs_register_under_deterministic_ids(
        self, scheduler: SchedulerManager
    ) -> None:
        # Deterministic, so re-registering on a restart replaces the job
        # rather than leaking a second copy of it.
        register_retry_sweep(scheduler, _noop, interval_seconds=15)
        register_replay_processor(scheduler, _noop, interval_seconds=10)
        register_statistics_rollup(scheduler, _noop, interval_seconds=900)
        register_idempotency_expiry_sweep(scheduler, _noop, interval_seconds=3_600)
        register_secret_expiry_sweep(scheduler, _noop, interval_seconds=3_600)

        assert scheduler.registry.get(RETRY_SWEEP_JOB_ID).job_type is JobType.SYSTEM
        assert scheduler.registry.get(REPLAY_PROCESSOR_JOB_ID).job_type is JobType.SYSTEM
        assert scheduler.registry.get(STATISTICS_ROLLUP_JOB_ID).job_type is JobType.SYSTEM
        assert scheduler.registry.get(IDEMPOTENCY_EXPIRY_SWEEP_JOB_ID).job_type is JobType.SYSTEM
        assert scheduler.registry.get(SECRET_EXPIRY_SWEEP_JOB_ID).job_type is JobType.SYSTEM
        assert len(scheduler.registry.list_jobs()) == 5

    async def test_a_schedule_carries_its_interval(self, scheduler: SchedulerManager) -> None:
        # A FIXED_RATE schedule without one is accepted by the dataclass
        # and then never fires -- the quietest possible failure for a
        # background job.
        register_retry_sweep(scheduler, _noop, interval_seconds=15)
        job = scheduler.registry.get(RETRY_SWEEP_JOB_ID)
        assert job.schedule.schedule_type is FrameworkScheduleType.FIXED_RATE
        assert job.schedule.interval == timedelta(seconds=15)

    async def test_every_jobs_schedule_carries_its_own_interval(
        self, scheduler: SchedulerManager
    ) -> None:
        register_replay_processor(scheduler, _noop, interval_seconds=10)
        register_statistics_rollup(scheduler, _noop, interval_seconds=900)
        register_idempotency_expiry_sweep(scheduler, _noop, interval_seconds=3_600)
        register_secret_expiry_sweep(scheduler, _noop, interval_seconds=1_800)

        assert scheduler.registry.get(REPLAY_PROCESSOR_JOB_ID).schedule.interval == timedelta(
            seconds=10
        )
        assert scheduler.registry.get(STATISTICS_ROLLUP_JOB_ID).schedule.interval == timedelta(
            seconds=900
        )
        assert scheduler.registry.get(
            IDEMPOTENCY_EXPIRY_SWEEP_JOB_ID
        ).schedule.interval == timedelta(seconds=3_600)
        assert scheduler.registry.get(SECRET_EXPIRY_SWEEP_JOB_ID).schedule.interval == timedelta(
            seconds=1_800
        )

    async def test_registration_computes_a_first_due_time(
        self, scheduler: SchedulerManager
    ) -> None:
        # Registered but never due is the other silent failure: the job
        # exists, the scheduler polls, nothing ever fires.
        job = register_statistics_rollup(scheduler, _noop, interval_seconds=900)
        assert job.next_run is not None

    async def test_each_jobs_metadata_names_its_own_component(
        self, scheduler: SchedulerManager
    ) -> None:
        register_retry_sweep(scheduler, _noop, interval_seconds=15)
        register_replay_processor(scheduler, _noop, interval_seconds=10)
        register_statistics_rollup(scheduler, _noop, interval_seconds=900)
        register_idempotency_expiry_sweep(scheduler, _noop, interval_seconds=3_600)
        register_secret_expiry_sweep(scheduler, _noop, interval_seconds=3_600)

        assert scheduler.registry.get(RETRY_SWEEP_JOB_ID).metadata["component"] == (
            "webhook-retry-sweep"
        )
        assert scheduler.registry.get(REPLAY_PROCESSOR_JOB_ID).metadata["component"] == (
            "webhook-replay-processor"
        )
        assert scheduler.registry.get(STATISTICS_ROLLUP_JOB_ID).metadata["component"] == (
            "webhook-statistics-rollup"
        )
        assert scheduler.registry.get(IDEMPOTENCY_EXPIRY_SWEEP_JOB_ID).metadata["component"] == (
            "webhook-idempotency-expiry-sweep"
        )
        assert scheduler.registry.get(SECRET_EXPIRY_SWEEP_JOB_ID).metadata["component"] == (
            "webhook-secret-expiry-sweep"
        )

    @pytest.mark.parametrize("interval", [0, -1, -600.5])
    async def test_a_non_positive_interval_is_refused(
        self, interval: float, scheduler: SchedulerManager
    ) -> None:
        # Zero would busy-loop the scheduler; negative is meaningless.
        with pytest.raises(ValueError, match="must be positive"):
            register_retry_sweep(scheduler, _noop, interval_seconds=interval)
        with pytest.raises(ValueError, match="must be positive"):
            register_replay_processor(scheduler, _noop, interval_seconds=interval)
        with pytest.raises(ValueError, match="must be positive"):
            register_statistics_rollup(scheduler, _noop, interval_seconds=interval)
        with pytest.raises(ValueError, match="must be positive"):
            register_idempotency_expiry_sweep(scheduler, _noop, interval_seconds=interval)
        with pytest.raises(ValueError, match="must be positive"):
            register_secret_expiry_sweep(scheduler, _noop, interval_seconds=interval)
