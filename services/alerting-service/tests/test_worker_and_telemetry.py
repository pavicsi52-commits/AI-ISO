"""Tests for the scheduled escalation worker, its scheduler
registration, and the telemetry helpers.

The worker is exercised against a real ``DatabaseFramework`` sharing
this test's own SAVEPOINT transaction (a scheduled job opens its own
session rather than receiving one via dependency injection), and the
registrar against a real ``SchedulerManager`` backed by real Redis and
RabbitMQ -- no in-memory fakes.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

import pytest
from opentelemetry.trace import get_tracer
from shared_core.cache.factory import create_cache_framework
from shared_core.cache.settings import CacheSettings
from shared_core.database.factory import DatabaseFramework
from shared_core.notifications.factory import create_notification_framework
from shared_core.queue.factory import QueueFramework
from shared_core.scheduler import Job, JobType, Schedule, create_scheduler_framework
from shared_core.scheduler import ScheduleType as FrameworkScheduleType
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from app.models.enums import AlertStatus
from app.repositories.alert_instance import AlertInstanceRepository
from app.scheduling.registrar import register_escalation_pass
from app.telemetry.tracing import (
    trace_acknowledgement,
    trace_correlation,
    trace_escalation,
    trace_notification_delivery,
    trace_routing,
    trace_rule_evaluation,
)
from app.workers.escalation_worker import build_dispatch_service, build_escalation_job_fn
from tests.conftest import make_alert, make_escalation_policy, redis_test_settings


async def _noop_publish(_event: object) -> None:
    return None


class TestEscalationWorker:
    async def test_scheduled_pass_escalates_a_due_alert(
        self,
        db_session: AsyncSession,
        db_session_factory: async_sessionmaker[AsyncSession],
        pg_engine: AsyncEngine,
    ) -> None:
        org = uuid.uuid4()
        await make_escalation_policy(
            db_session,
            organization_id=org,
            levels=[{"target_type": "user", "target_reference": "u1", "delay_seconds": 60}],
        )
        alert = await make_alert(
            db_session,
            organization_id=org,
            status=AlertStatus.OPEN,
            triggered_at=datetime.now(UTC) - timedelta(minutes=10),
        )

        database = DatabaseFramework(engine=pg_engine, session_factory=db_session_factory)
        job_fn = build_escalation_job_fn(
            org, database, create_notification_framework(), _noop_publish
        )
        await job_fn(_job())

        # Read back through a *fresh* session: the worker committed in its
        # own session, and this test's original session still holds the
        # pre-escalation copy in its identity map. A new session on the
        # same SAVEPOINT-isolated connection sees what was really written.
        async with db_session_factory() as verifying:
            refreshed = await AlertInstanceRepository(verifying).require_by_id(alert.id)
            assert refreshed.status == AlertStatus.ESCALATED

    async def test_pass_with_nothing_due_is_a_no_op(
        self,
        db_session: AsyncSession,
        db_session_factory: async_sessionmaker[AsyncSession],
        pg_engine: AsyncEngine,
    ) -> None:
        org = uuid.uuid4()
        alert = await make_alert(db_session, organization_id=org, status=AlertStatus.OPEN)

        database = DatabaseFramework(engine=pg_engine, session_factory=db_session_factory)
        job_fn = build_escalation_job_fn(
            org, database, create_notification_framework(), _noop_publish
        )
        await job_fn(_job())

        refreshed = await AlertInstanceRepository(db_session).require_by_id(alert.id)
        assert refreshed.status == AlertStatus.OPEN

    async def test_build_dispatch_service_is_fully_wired(self, db_session: AsyncSession) -> None:
        service = build_dispatch_service(db_session, create_notification_framework(), _noop_publish)
        assert await service.advance_escalations(uuid.uuid4()) == 0


def _job() -> Job:
    """A throwaway framework ``Job``; the closure ignores its argument."""

    async def _fn(_job: Job) -> None:
        return None

    return Job(
        job_id="test",
        job_name="test",
        job_type=JobType.SYSTEM,
        fn=_fn,
        schedule=Schedule(
            schedule_type=FrameworkScheduleType.FIXED_RATE, interval=timedelta(seconds=60)
        ),
    )


class TestSchedulerRegistrar:
    async def test_registers_a_recurring_job(self, real_queue_framework: QueueFramework) -> None:
        cache = await create_cache_framework(CacheSettings(redis=redis_test_settings()))
        manager = create_scheduler_framework(
            real_queue_framework.manager, cache.client, queue_name="alerting_test_scheduler"
        )
        organization_id = uuid.uuid4()

        async def _fn(_job: Job) -> None:
            return None

        job = register_escalation_pass(manager, organization_id, _fn, interval_seconds=60)
        assert job.job_id == f"alert-escalation-{organization_id}"
        await cache.shutdown()

    async def test_reregistration_replaces_in_place(
        self, real_queue_framework: QueueFramework
    ) -> None:
        """A deterministic job_id must not leak a second, orphaned job."""
        cache = await create_cache_framework(CacheSettings(redis=redis_test_settings()))
        manager = create_scheduler_framework(
            real_queue_framework.manager, cache.client, queue_name="alerting_test_scheduler"
        )
        organization_id = uuid.uuid4()

        async def _fn(_job: Job) -> None:
            return None

        first = register_escalation_pass(manager, organization_id, _fn, interval_seconds=60)
        second = register_escalation_pass(manager, organization_id, _fn, interval_seconds=120)
        assert first.job_id == second.job_id
        await cache.shutdown()

    async def test_non_positive_interval_is_rejected(
        self, real_queue_framework: QueueFramework
    ) -> None:
        cache = await create_cache_framework(CacheSettings(redis=redis_test_settings()))
        manager = create_scheduler_framework(
            real_queue_framework.manager, cache.client, queue_name="alerting_test_scheduler"
        )

        async def _fn(_job: Job) -> None:
            return None

        with pytest.raises(ValueError, match="must be positive"):
            register_escalation_pass(manager, uuid.uuid4(), _fn, interval_seconds=0)
        await cache.shutdown()


class TestTelemetry:
    def test_every_trace_helper_yields_a_span(self) -> None:
        tracer = get_tracer("tests")
        alert_id = str(uuid.uuid4())
        with trace_rule_evaluation(tracer, rule_id=str(uuid.uuid4())) as span:
            assert span is not None
        with trace_correlation(tracer, alert_id=alert_id) as span:
            assert span is not None
        with trace_notification_delivery(tracer, alert_id=alert_id, channel="email") as span:
            assert span is not None
        with trace_escalation(tracer, alert_id=alert_id) as span:
            assert span is not None
        with trace_routing(tracer, alert_id=alert_id) as span:
            assert span is not None
        with trace_acknowledgement(tracer, alert_id=alert_id) as span:
            assert span is not None
