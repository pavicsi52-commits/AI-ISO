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
from tests.conftest import rabbitmq_test_settings, redis_test_settings

from app.workers.registrar import (
    APPROVAL_EXPIRY_SWEEP_JOB_ID,
    CONFLICT_SWEEP_JOB_ID,
    MAINTENANCE_SWEEP_JOB_ID,
    STATISTICS_ROLLUP_JOB_ID,
    register_approval_expiry_sweep,
    register_conflict_sweep,
    register_maintenance_sweep,
    register_statistics_rollup,
)

pytestmark = pytest.mark.asyncio


async def _noop(_job: Job) -> None:
    """A job body that does nothing, for registration tests."""


@pytest_asyncio.fixture
async def scheduler() -> AsyncIterator[SchedulerManager]:
    """A real scheduler manager, built the way the factory builds it."""
    queue = await create_queue_framework(rabbitmq_test_settings())
    cache = await create_cache_framework(CacheSettings(redis=redis_test_settings()))
    manager = create_scheduler_framework(
        queue.manager, cache.client, queue_name="change_management_test_queue"
    )
    yield manager
    await cache.shutdown()
    await queue.shutdown()


class TestJobRegistration:
    async def test_all_four_jobs_register_under_deterministic_ids(
        self, scheduler: SchedulerManager
    ) -> None:
        # Deterministic, so re-registering on a restart replaces the job
        # rather than leaking a second copy of it.
        register_conflict_sweep(scheduler, _noop, interval_seconds=60)
        register_approval_expiry_sweep(scheduler, _noop, interval_seconds=60)
        register_statistics_rollup(scheduler, _noop, interval_seconds=900)
        register_maintenance_sweep(scheduler, _noop, interval_seconds=3_600)

        assert scheduler.registry.get(CONFLICT_SWEEP_JOB_ID).job_type is JobType.SYSTEM
        assert scheduler.registry.get(APPROVAL_EXPIRY_SWEEP_JOB_ID).job_type is JobType.SYSTEM
        assert scheduler.registry.get(STATISTICS_ROLLUP_JOB_ID).job_type is JobType.SYSTEM
        assert scheduler.registry.get(MAINTENANCE_SWEEP_JOB_ID).job_type is JobType.SYSTEM
        assert len(scheduler.registry.list_jobs()) == 4

    async def test_a_schedule_carries_its_interval(self, scheduler: SchedulerManager) -> None:
        # A FIXED_RATE schedule without one is accepted by the dataclass
        # and then never fires -- the quietest possible failure for a
        # background job.
        register_conflict_sweep(scheduler, _noop, interval_seconds=60)
        job = scheduler.registry.get(CONFLICT_SWEEP_JOB_ID)
        assert job.schedule.schedule_type is FrameworkScheduleType.FIXED_RATE
        assert job.schedule.interval == timedelta(seconds=60)

    async def test_registration_computes_a_first_due_time(
        self, scheduler: SchedulerManager
    ) -> None:
        # Registered but never due is the other silent failure: the job
        # exists, the scheduler polls, nothing ever fires.
        job = register_maintenance_sweep(scheduler, _noop, interval_seconds=3_600)
        assert job.next_run is not None

    async def test_the_manager_returns_the_registered_job_not_a_never_scheduled_copy(
        self, scheduler: SchedulerManager
    ) -> None:
        # _register returns the manager's own object, not the local one
        # it built -- the local copy reads as never scheduled.
        job = register_statistics_rollup(scheduler, _noop, interval_seconds=900)
        assert job is scheduler.registry.get(STATISTICS_ROLLUP_JOB_ID)

    @pytest.mark.parametrize("interval", [0, -1, -600.5])
    async def test_a_non_positive_interval_is_refused(
        self, interval: float, scheduler: SchedulerManager
    ) -> None:
        # Zero would busy-loop the scheduler; negative is meaningless.
        with pytest.raises(ValueError, match="must be positive"):
            register_conflict_sweep(scheduler, _noop, interval_seconds=interval)
        with pytest.raises(ValueError, match="must be positive"):
            register_approval_expiry_sweep(scheduler, _noop, interval_seconds=interval)
        with pytest.raises(ValueError, match="must be positive"):
            register_statistics_rollup(scheduler, _noop, interval_seconds=interval)
        with pytest.raises(ValueError, match="must be positive"):
            register_maintenance_sweep(scheduler, _noop, interval_seconds=interval)
