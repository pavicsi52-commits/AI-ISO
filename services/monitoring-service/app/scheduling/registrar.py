"""Recurring collector/synthetic-test registration against
``shared_core.scheduler``.

This module only *maps* a
:class:`~app.models.monitoring_collector.MonitoringCollector`/
:class:`~app.models.monitoring_synthetic_test.MonitoringSyntheticTest`
row's own ``interval_seconds`` onto that framework's own
:class:`~shared_core.scheduler.Schedule`/:class:`~shared_core.scheduler.Job`
shapes (``FIXED_RATE``, reusing the real ``JobType.MONITORING`` value
the framework already names for exactly this use) and registers it --
the actual interval computation, distributed locking, leader election,
and retry machinery all live in ``packages/shared-core/scheduler``
(Prompt 026), the same "framework owns the loop, caller owns the job
definitions" split ``services/workflow-runtime-service``'s own
``app/scheduling/registrar.py`` already established for an analogous
timer-to-schedule mapping.
"""

from __future__ import annotations

from datetime import timedelta

from shared_core.scheduler import Job, JobFn, JobType, Schedule, SchedulerManager
from shared_core.scheduler import ScheduleType as FrameworkScheduleType

from app.models.monitoring_collector import MonitoringCollector
from app.models.monitoring_synthetic_test import MonitoringSyntheticTest


def register_collector(manager: SchedulerManager, collector: MonitoringCollector, fn: JobFn) -> Job:
    """Register *collector* with *manager* on its own fixed-rate interval.

    Uses ``f"collector-{collector.id}"`` as the framework job's own
    ``job_id`` (rather than a freshly-random one) so that re-registering
    the same :class:`MonitoringCollector` replaces its prior
    registration in place instead of leaking a second, orphaned one.
    """
    job = Job(
        job_id=f"collector-{collector.id}",
        job_name=f"monitoring-collector-{collector.id}",
        job_type=JobType.MONITORING,
        fn=fn,
        schedule=Schedule(
            schedule_type=FrameworkScheduleType.FIXED_RATE,
            interval=timedelta(seconds=collector.interval_seconds),
        ),
        organization_id=str(collector.organization_id),
        metadata={"collector_id": str(collector.id)},
    )
    manager.register_job(job)
    return job


def register_synthetic_test(
    manager: SchedulerManager, test: MonitoringSyntheticTest, fn: JobFn
) -> Job:
    """Register *test* with *manager* on its own fixed-rate interval."""
    job = Job(
        job_id=f"synthetic-{test.id}",
        job_name=f"monitoring-synthetic-{test.id}",
        job_type=JobType.MONITORING,
        fn=fn,
        schedule=Schedule(
            schedule_type=FrameworkScheduleType.FIXED_RATE,
            interval=timedelta(seconds=test.interval_seconds),
        ),
        organization_id=str(test.organization_id),
        metadata={"synthetic_test_id": str(test.id)},
    )
    manager.register_job(job)
    return job


__all__ = ["register_collector", "register_synthetic_test"]
