"""Tests for :mod:`app.workers.collection_worker` -- the ``Job.fn``
closures :mod:`app.scheduling.registrar` registers per active
collector/synthetic test. Builds a real
``shared_core.database.factory.DatabaseFramework`` sharing this test's
own SAVEPOINT-isolated connection (via ``db_session_factory``), so data
seeded through ``db_session`` is visible to the worker's own
independently-opened session.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Any

import httpx
import pytest
from shared_core.database.factory import DatabaseFramework
from shared_core.events.base import DomainEvent
from shared_core.scheduler import Job, JobType, Schedule
from shared_core.scheduler import ScheduleType as FrameworkScheduleType
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from app.collectors.context import CollectorContext
from app.collectors.registry import CollectorRegistry
from app.models.enums import MonitoringTargetType
from app.repositories.monitoring_health import MonitoringHealthRepository
from app.repositories.monitoring_target import MonitoringTargetRepository
from app.workers.collection_worker import build_collector_job_fn, build_synthetic_test_job_fn
from tests.conftest import build_collector_context, make_collector, make_synthetic_test, make_target


@pytest.fixture
async def context() -> AsyncIterator[CollectorContext]:
    async with httpx.AsyncClient() as client:
        yield build_collector_context(client)


class _EventRecorder:
    def __init__(self) -> None:
        self.events: list[DomainEvent] = []

    async def __call__(self, event: DomainEvent) -> None:
        self.events.append(event)


def _fake_job(job_id: str) -> Job:
    async def _noop(_job: Job) -> None:
        return None

    return Job(
        job_id=job_id,
        job_name=job_id,
        job_type=JobType.MONITORING,
        fn=_noop,
        schedule=Schedule(schedule_type=FrameworkScheduleType.IMMEDIATE),
    )


class TestBuildCollectorJobFn:
    async def test_runs_collector_against_matching_targets(
        self,
        db_session: AsyncSession,
        db_session_factory: async_sessionmaker[AsyncSession],
        pg_engine: AsyncEngine,
        context: CollectorContext,
    ) -> None:
        target = await make_target(db_session, target_metadata={"host": "127.0.0.1"})
        collector = await make_collector(
            db_session,
            organization_id=target.organization_id,
            collector_key="dns",
            target_types=[target.target_type],
        )
        database = DatabaseFramework(engine=pg_engine, session_factory=db_session_factory)
        registry = CollectorRegistry()

        async def _fake_dns(
            _collector: object, _target: object, _context: object
        ) -> dict[str, Any]:
            return {"resolved": True}

        registry.register("dns", _fake_dns)
        recorder = _EventRecorder()

        job_fn = build_collector_job_fn(collector, database, registry, context, recorder)
        await job_fn(_fake_job("collector-test"))

        health_repo = MonitoringHealthRepository(db_session)
        results = await health_repo.list_for_target(target.id)
        assert len(results) == 1

    async def test_no_matching_targets_is_a_noop(
        self,
        db_session: AsyncSession,
        db_session_factory: async_sessionmaker[AsyncSession],
        pg_engine: AsyncEngine,
        context: CollectorContext,
    ) -> None:
        collector = await make_collector(
            db_session, collector_key="dns", target_types=["kubernetes"]
        )
        database = DatabaseFramework(engine=pg_engine, session_factory=db_session_factory)
        registry = CollectorRegistry()
        recorder = _EventRecorder()

        job_fn = build_collector_job_fn(collector, database, registry, context, recorder)
        await job_fn(_fake_job("collector-empty"))

        assert recorder.events == []

    async def test_broken_collector_is_handled_gracefully(
        self,
        db_session: AsyncSession,
        db_session_factory: async_sessionmaker[AsyncSession],
        pg_engine: AsyncEngine,
        context: CollectorContext,
    ) -> None:
        """``MonitoringCollectionService._collect_one`` catches a broken
        collector function and records it as UNHEALTHY rather than
        raising -- the job completes normally.
        """
        target = await make_target(db_session)
        collector = await make_collector(
            db_session,
            organization_id=target.organization_id,
            collector_key="broken",
            target_types=[target.target_type],
        )
        database = DatabaseFramework(engine=pg_engine, session_factory=db_session_factory)
        registry = CollectorRegistry()

        async def _broken(_collector: object, _target: object, _context: object) -> dict[str, Any]:
            raise RuntimeError("collector itself is misconfigured")

        registry.register("broken", _broken)
        recorder = _EventRecorder()
        job_fn = build_collector_job_fn(collector, database, registry, context, recorder)

        await job_fn(_fake_job("collector-broken"))
        health_repo = MonitoringHealthRepository(db_session)
        results = await health_repo.list_for_target(target.id)
        assert str(results[0].status) == "unhealthy"

    async def test_unexpected_exception_is_reraised(
        self,
        db_session: AsyncSession,
        db_session_factory: async_sessionmaker[AsyncSession],
        pg_engine: AsyncEngine,
        context: CollectorContext,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """A failure genuinely outside
        :meth:`MonitoringCollectionService.run_collector`'s own internal
        per-collector guard must still propagate out of the scheduled
        job, so the framework's own retry/backoff machinery can see it.
        """
        target = await make_target(db_session)
        collector = await make_collector(
            db_session, organization_id=target.organization_id, target_types=[target.target_type]
        )
        database = DatabaseFramework(engine=pg_engine, session_factory=db_session_factory)
        registry = CollectorRegistry()
        recorder = _EventRecorder()

        async def _broken_run(self: object, *_args: object, **_kwargs: object) -> None:
            raise RuntimeError("boom")

        monkeypatch.setattr(
            "app.workers.collection_worker.MonitoringCollectionService.run_collector", _broken_run
        )

        job_fn = build_collector_job_fn(collector, database, registry, context, recorder)
        with pytest.raises(RuntimeError, match="boom"):
            await job_fn(_fake_job("collector-unexpected"))


class TestBuildSyntheticTestJobFn:
    async def test_runs_synthetic_test_for_registered_target(
        self,
        db_session: AsyncSession,
        db_session_factory: async_sessionmaker[AsyncSession],
        pg_engine: AsyncEngine,
        context: CollectorContext,
    ) -> None:
        target = await make_target(db_session, target_metadata={"host": "localhost"})
        test = await make_synthetic_test(
            db_session,
            organization_id=target.organization_id,
            target_id=target.id,
            check_type="dns",  # type: ignore[arg-type]
        )
        database = DatabaseFramework(engine=pg_engine, session_factory=db_session_factory)
        recorder = _EventRecorder()

        job_fn = build_synthetic_test_job_fn(test, database, context, recorder)
        await job_fn(_fake_job("synthetic-test"))

        health_repo = MonitoringHealthRepository(db_session)
        results = await health_repo.list_for_target(target.id)
        assert len(results) == 1

    async def test_runs_synthetic_test_without_registered_target(
        self,
        db_session: AsyncSession,
        db_session_factory: async_sessionmaker[AsyncSession],
        pg_engine: AsyncEngine,
        context: CollectorContext,
    ) -> None:
        test = await make_synthetic_test(
            db_session,
            target_id=None,
            check_type="dns",  # type: ignore[arg-type]
            parameters={"host": "localhost"},
        )
        database = DatabaseFramework(engine=pg_engine, session_factory=db_session_factory)
        recorder = _EventRecorder()

        job_fn = build_synthetic_test_job_fn(test, database, context, recorder)
        await job_fn(_fake_job("synthetic-no-target"))

        virtual_target = await MonitoringTargetRepository(db_session).get_by_external_id(
            test.organization_id, MonitoringTargetType.CUSTOM_TARGET, f"synthetic-test:{test.id}"
        )
        assert virtual_target is not None
        health_repo = MonitoringHealthRepository(db_session)
        results = await health_repo.list_for_target(virtual_target.id)
        assert len(results) == 1

    async def test_synthetic_test_failure_is_logged_and_reraised(
        self,
        db_session: AsyncSession,
        db_session_factory: async_sessionmaker[AsyncSession],
        pg_engine: AsyncEngine,
        context: CollectorContext,
    ) -> None:
        test = await make_synthetic_test(
            db_session, target_id=None, check_type="http"  # type: ignore[arg-type]
        )
        # No 'url' parameter -> ValidationError inside run_synthetic_test,
        # caught by MonitoringSyntheticExecutionService.run() and recorded
        # as a failure -- not re-raised by the service itself.
        database = DatabaseFramework(engine=pg_engine, session_factory=db_session_factory)
        recorder = _EventRecorder()

        job_fn = build_synthetic_test_job_fn(test, database, context, recorder)
        await job_fn(_fake_job("synthetic-failure"))

        virtual_target = await MonitoringTargetRepository(db_session).get_by_external_id(
            test.organization_id, MonitoringTargetType.CUSTOM_TARGET, f"synthetic-test:{test.id}"
        )
        assert virtual_target is not None
        health_repo = MonitoringHealthRepository(db_session)
        results = await health_repo.list_for_target(virtual_target.id)
        assert str(results[0].status) == "unhealthy"

    async def test_unexpected_exception_is_reraised(
        self,
        db_session: AsyncSession,
        db_session_factory: async_sessionmaker[AsyncSession],
        pg_engine: AsyncEngine,
        context: CollectorContext,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """A failure genuinely outside
        :meth:`MonitoringSyntheticExecutionService.run`'s own internal
        try/except (which always resolves to a failure status rather
        than raising) must still propagate out of the scheduled job, so
        the framework's own retry/backoff machinery can see it.
        """
        test = await make_synthetic_test(db_session, target_id=None, check_type="http")  # type: ignore[arg-type]
        database = DatabaseFramework(engine=pg_engine, session_factory=db_session_factory)
        recorder = _EventRecorder()

        async def _broken_run(self: object, *_args: object, **_kwargs: object) -> None:
            raise RuntimeError("boom")

        monkeypatch.setattr(
            "app.workers.collection_worker.MonitoringSyntheticExecutionService.run", _broken_run
        )

        job_fn = build_synthetic_test_job_fn(test, database, context, recorder)
        with pytest.raises(RuntimeError, match="boom"):
            await job_fn(_fake_job("synthetic-unexpected"))
