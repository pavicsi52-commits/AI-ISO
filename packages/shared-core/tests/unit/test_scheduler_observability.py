"""Tests for audit.py, history.py, metrics.py, and health.py."""

from __future__ import annotations

from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta

import pytest
from aio_pika.abc import AbstractRobustConnection
from fakeredis import FakeAsyncRedis
from redis.asyncio import Redis
from shared_core.enums.health_status import HealthStatus
from shared_core.scheduler import audit
from shared_core.scheduler import metrics as scheduler_metrics
from shared_core.scheduler.executor import ExecutionResult
from shared_core.scheduler.health import build_health_report
from shared_core.scheduler.heartbeat import HeartbeatRegistry
from shared_core.scheduler.history import HistoryStore
from shared_core.scheduler.job import Job, JobType, build_job
from shared_core.scheduler.leader import LeaderElection, cluster_has_leader
from shared_core.scheduler.registry import JobRegistry
from shared_core.scheduler.schedule import Schedule, ScheduleType


@pytest.fixture
async def redis_client() -> AsyncIterator[FakeAsyncRedis]:
    client = FakeAsyncRedis()
    yield client
    await client.aclose()


# --- audit.py: every function is a thin call to logger.audit(); this
# confirms none of them raise and that the module's public surface is
# exactly what's documented.


def test_audit_functions_do_not_raise() -> None:
    audit.audit_registration("job-1", "nightly-report")
    audit.audit_modification("job-1", owner="ops")
    audit.audit_deletion("job-1")
    audit.audit_execution("job-1", worker_node_id="node-a", outcome="success", attempts=1)
    audit.audit_retry("job-1", attempt=2)
    audit.audit_pause("job-1")
    audit.audit_resume("job-1")
    audit.audit_cancellation("job-1")


def test_audit_all_exports_every_function() -> None:
    assert set(audit.__all__) == {
        "audit_cancellation",
        "audit_deletion",
        "audit_execution",
        "audit_modification",
        "audit_pause",
        "audit_registration",
        "audit_resume",
        "audit_retry",
    }


# --- history.py ---


def _result(
    job_id: str, *, succeeded: bool, attempts: int = 1, error: str | None = None
) -> ExecutionResult:
    started = datetime(2026, 1, 1, tzinfo=UTC)
    return ExecutionResult(
        job_id=job_id,
        succeeded=succeeded,
        attempts=attempts,
        started_at=started,
        finished_at=started + timedelta(seconds=2),
        error=error,
    )


def test_history_store_record_returns_a_matching_entry() -> None:
    store = HistoryStore()

    entry = store.record("node-a", _result("job-1", succeeded=True))

    assert entry.job_id == "job-1"
    assert entry.worker_node_id == "node-a"
    assert entry.duration_seconds == 2.0
    assert entry.status == "succeeded"


def test_history_store_status_reports_failed() -> None:
    store = HistoryStore()

    entry = store.record("node-a", _result("job-1", succeeded=False, error="boom"))

    assert entry.status == "failed"


def test_history_store_for_job_filters_by_job_id() -> None:
    store = HistoryStore()
    store.record("node-a", _result("job-1", succeeded=True))
    store.record("node-a", _result("job-2", succeeded=True))

    assert [entry.job_id for entry in store.for_job("job-1")] == ["job-1"]


def test_history_store_recent_returns_newest_first() -> None:
    store = HistoryStore()
    store.record("node-a", _result("job-1", succeeded=True))
    store.record("node-a", _result("job-2", succeeded=True))

    assert [entry.job_id for entry in store.recent()] == ["job-2", "job-1"]


def test_history_store_recent_honors_a_limit() -> None:
    store = HistoryStore()
    store.record("node-a", _result("job-1", succeeded=True))
    store.record("node-a", _result("job-2", succeeded=True))

    assert [entry.job_id for entry in store.recent(limit=1)] == ["job-2"]


def test_history_store_failure_count() -> None:
    store = HistoryStore()
    store.record("node-a", _result("job-1", succeeded=False))
    store.record("node-a", _result("job-1", succeeded=True))
    store.record("node-a", _result("job-1", succeeded=False))

    assert store.failure_count("job-1") == 2


def test_history_store_respects_max_entries() -> None:
    store = HistoryStore(max_entries=2)
    store.record("node-a", _result("job-1", succeeded=True))
    store.record("node-a", _result("job-2", succeeded=True))
    store.record("node-a", _result("job-3", succeeded=True))

    assert [entry.job_id for entry in store.recent()] == ["job-3", "job-2"]


# --- metrics.py ---


def test_record_execution_increments_completed_on_success() -> None:
    before = scheduler_metrics.scheduler_completed_jobs_total._value.get()

    scheduler_metrics.record_execution(succeeded=True, duration_seconds=1.5)

    assert scheduler_metrics.scheduler_completed_jobs_total._value.get() == before + 1


def test_record_execution_increments_failed_on_failure() -> None:
    before = scheduler_metrics.scheduler_failed_jobs_total._value.get()

    scheduler_metrics.record_execution(succeeded=False, duration_seconds=1.5)

    assert scheduler_metrics.scheduler_failed_jobs_total._value.get() == before + 1


def test_record_execution_records_retries() -> None:
    before = scheduler_metrics.scheduler_retries_total._value.get()

    scheduler_metrics.record_execution(succeeded=True, duration_seconds=1.0, retries=3)

    assert scheduler_metrics.scheduler_retries_total._value.get() == before + 3


def test_gauge_setters_set_the_expected_value() -> None:
    scheduler_metrics.record_registered(5)
    scheduler_metrics.record_running(2)
    scheduler_metrics.set_worker_count(3)
    scheduler_metrics.set_queue_depth(7)
    scheduler_metrics.set_execution_rate(1.25)
    scheduler_metrics.set_uptime_seconds(42.0)

    assert scheduler_metrics.scheduler_registered_jobs._value.get() == 5
    assert scheduler_metrics.scheduler_running_jobs._value.get() == 2
    assert scheduler_metrics.scheduler_worker_count._value.get() == 3
    assert scheduler_metrics.scheduler_queue_depth._value.get() == 7
    assert scheduler_metrics.scheduler_execution_rate._value.get() == 1.25
    assert scheduler_metrics.scheduler_uptime_seconds._value.get() == 42.0


# --- leader.py: cluster_has_leader ---


async def test_cluster_has_leader_false_when_no_one_has_campaigned(redis_client: Redis) -> None:
    assert await cluster_has_leader(redis_client) is False


async def test_cluster_has_leader_true_once_a_node_wins(redis_client: Redis) -> None:
    election = LeaderElection(redis_client, "node-a")
    await election.campaign()

    assert await cluster_has_leader(redis_client) is True


# --- health.py ---


async def test_build_health_report_unhealthy_with_no_workers(
    redis_client: Redis, rabbitmq_connection: AbstractRobustConnection
) -> None:
    registry = JobRegistry()
    heartbeats = HeartbeatRegistry(redis_client)

    report = await build_health_report(registry, heartbeats, redis_client, rabbitmq_connection)

    assert report.worker_status == HealthStatus.UNHEALTHY
    assert report.heartbeat_status == HealthStatus.UNHEALTHY
    assert report.leader_status == HealthStatus.DEGRADED
    assert report.status == HealthStatus.UNHEALTHY
    assert report.active_worker_count == 0


async def test_build_health_report_healthy_with_a_worker_and_leader(
    redis_client: Redis, rabbitmq_connection: AbstractRobustConnection
) -> None:
    async def _noop(_job: Job) -> None:
        pass

    registry = JobRegistry()
    job = build_job(
        job_name="job",
        job_type=JobType.BACKGROUND,
        fn=_noop,
        schedule=Schedule(schedule_type=ScheduleType.IMMEDIATE),
    )
    registry.register(job)
    heartbeats = HeartbeatRegistry(redis_client)
    await heartbeats.beat("node-a")
    election = LeaderElection(redis_client, "node-a")
    await election.campaign()

    report = await build_health_report(registry, heartbeats, redis_client, rabbitmq_connection)

    assert report.worker_status == HealthStatus.HEALTHY
    assert report.leader_status == HealthStatus.HEALTHY
    assert report.active_worker_count == 1
    assert report.registered_job_count == 1
