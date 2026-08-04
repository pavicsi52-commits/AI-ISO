"""The four background workers, against real PostgreSQL.

Each worker gets its own session per organization in production; here
that session factory is the same SAVEPOINT-bound one every other
fixture uses, so data created through the service fixtures in the same
test is visible to the worker's own sessions -- see
``tests/conftest.py``'s ``db_session_factory``.

**Reading back what a worker's own session committed.** A worker
commits through a *new* ``AsyncSession`` object bound to the same
underlying connection, not the fixture's ``db_session``. A fresh query
for rows the fixture session never loaded (a list, a count) sees that
commit immediately -- same connection, same transaction. Re-reading an
object the fixture session already loaded into its own identity map
does not: with ``expire_on_commit=False`` that object is never
refreshed just because another session on the same connection
committed. Those reads go through a brand-new ``db_session_factory()``
session instead, exactly as ``services/incident-management-service``'s
own ``test_workers.py`` does for the same reason.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from tests.conftest import RecordingPublisher, ago, soon, utcnow

from app.models.enums import JobType, ScheduledJobStatus
from app.models.history import JobFailure
from app.models.job import ScheduledJob
from app.models.maintenance import MaintenanceWindow
from app.repositories.history import JobFailureRepository
from app.repositories.job import ScheduledJobRepository
from app.services.execution import ExecutionService
from app.services.job import JobService
from app.services.maintenance import MaintenanceWindowService
from app.workers.due_schedule_sweep import DueScheduleSweepWorker
from app.workers.maintenance_sweep import MaintenanceSweepWorker
from app.workers.retry_sweep import RetrySweepWorker
from app.workers.statistics import StatisticsWorker

pytestmark = pytest.mark.asyncio


def _flaky_after(
    real_factory: async_sessionmaker[AsyncSession], *, fail_on_call: int
) -> Callable[[], AsyncSession]:
    """A session factory that raises on its *fail_on_call*-th invocation only.

    Simulates one organization's own session breaking mid-sweep without
    touching any other organization's -- the workers open one session
    per organization by calling ``session_factory()`` with no
    arguments, so the only way to target "one organization's session"
    from outside is by call order.
    """
    calls = {"n": 0}

    def factory() -> AsyncSession:
        calls["n"] += 1
        if calls["n"] == fail_on_call:
            raise RuntimeError("Simulated per-organization session failure.")
        return real_factory()

    return factory


class TestDueScheduleSweepWorker:
    async def test_tick_dispatches_a_due_cron_job(
        self,
        db_session_factory: async_sessionmaker[AsyncSession],
        make_job_with_cron_trigger,
        executions_repo,
        organization_id,
    ) -> None:
        job = await make_job_with_cron_trigger(cron_expression="* * * * *")
        worker = DueScheduleSweepWorker(db_session_factory)
        counts = await worker.tick()
        assert counts["dispatched"] >= 1
        executions = await executions_repo.list_for_job(organization_id, job.id)
        assert len(executions) >= 1

    async def test_a_paused_jobs_due_schedule_is_skipped_not_dispatched(
        self,
        db_session_factory: async_sessionmaker[AsyncSession],
        make_job_with_cron_trigger,
        job_service: JobService,
        executions_repo,
        organization_id,
    ) -> None:
        job = await make_job_with_cron_trigger(cron_expression="* * * * *")
        await job_service.pause(organization_id, job.id)
        worker = DueScheduleSweepWorker(db_session_factory)
        counts = await worker.tick()
        assert counts["dispatched"] == 0
        executions = await executions_repo.list_for_job(organization_id, job.id)
        assert executions == []

    async def test_an_active_maintenance_window_suppresses_a_normal_priority_due_job(
        self,
        db_session_factory: async_sessionmaker[AsyncSession],
        make_job_with_cron_trigger,
        maintenance_service: MaintenanceWindowService,
        executions_repo,
        organization_id,
    ) -> None:
        job = await make_job_with_cron_trigger(cron_expression="* * * * *")
        await maintenance_service.create_window(
            organization_id,
            title="Live now",
            starts_at=ago(),
            ends_at=soon(),
            allow_critical_override=False,
        )
        worker = DueScheduleSweepWorker(db_session_factory)
        counts = await worker.tick()
        assert counts["suppressed"] >= 1
        assert counts["dispatched"] == 0
        executions = await executions_repo.list_for_job(organization_id, job.id)
        assert executions == []

    async def test_run_job_delegates_to_tick(
        self, db_session_factory: async_sessionmaker[AsyncSession]
    ) -> None:
        worker = DueScheduleSweepWorker(db_session_factory)
        await worker.run_job(None)  # type: ignore[arg-type]

    async def test_a_tick_with_no_organizations_reports_zero(
        self, db_session_factory: async_sessionmaker[AsyncSession]
    ) -> None:
        worker = DueScheduleSweepWorker(db_session_factory, max_per_tick=0)
        counts = await worker.tick()
        assert counts == {"organizations": 0, "dispatched": 0, "suppressed": 0}


class TestRetrySweepWorker:
    async def test_tick_dispatches_a_due_retry_and_marks_it_retried(
        self,
        db_session_factory: async_sessionmaker[AsyncSession],
        execution_service: ExecutionService,
        failures_repo,
        executions_repo,
        make_job,
        organization_id,
    ) -> None:
        job = await make_job()
        execution = await execution_service.dispatch(
            organization_id, job.id, trigger_source="manual"
        )
        failure = await failures_repo.create(
            JobFailure(
                organization_id=organization_id,
                job_id=job.id,
                execution_id=execution.id,
                occurred_at=utcnow(),
                failure_reason="Simulated failure",
                error_detail="Something went wrong downstream.",
                is_terminal=False,
                retried=False,
                retry_at=ago(),
            )
        )
        before = await executions_repo.list_for_job(organization_id, job.id)

        worker = RetrySweepWorker(db_session_factory)
        retried = await worker.tick()

        assert retried >= 1
        after = await executions_repo.list_for_job(organization_id, job.id)
        assert len(after) > len(before)

        # A fresh session, not the fixture's: the worker committed through
        # its own session on the same connection, and re-reading through
        # the identity map that created this row would return its stale,
        # pre-tick copy rather than a real re-fetch.
        async with db_session_factory() as fresh:
            refreshed = await JobFailureRepository(fresh).require_in_org(
                organization_id, failure.id
            )
            assert refreshed.retried is True

    async def test_run_job_delegates_to_tick(
        self, db_session_factory: async_sessionmaker[AsyncSession]
    ) -> None:
        worker = RetrySweepWorker(db_session_factory)
        await worker.run_job(None)  # type: ignore[arg-type]

    async def test_a_tick_with_no_organizations_reports_zero(
        self, db_session_factory: async_sessionmaker[AsyncSession]
    ) -> None:
        worker = RetrySweepWorker(db_session_factory, max_per_tick=0)
        assert await worker.tick() == 0


class TestStatisticsWorker:
    async def test_tick_recomputes_every_organization_and_a_row_now_exists(
        self,
        db_session_factory: async_sessionmaker[AsyncSession],
        statistics_repo,
        make_job,
        organization_id,
    ) -> None:
        await make_job()
        worker = StatisticsWorker(db_session_factory)
        done = await worker.tick()
        assert done >= 1
        latest = await statistics_repo.latest(organization_id)
        assert latest is not None

    async def test_run_job_delegates_to_tick(
        self, db_session_factory: async_sessionmaker[AsyncSession]
    ) -> None:
        worker = StatisticsWorker(db_session_factory)
        await worker.run_job(None)  # type: ignore[arg-type]

    async def test_a_tick_with_no_organizations_succeeds_with_zero(
        self, db_session_factory: async_sessionmaker[AsyncSession]
    ) -> None:
        worker = StatisticsWorker(db_session_factory, max_per_tick=0)
        assert await worker.tick() == 0

    async def test_a_failure_recomputing_one_organization_does_not_poison_the_next(
        self, db_session_factory: async_sessionmaker[AsyncSession], organization_id
    ) -> None:
        other_organization_id = uuid4()
        # Two organizations, each with one job, so the worker's own
        # per-organization loop has two iterations to isolate between.
        async with db_session_factory() as session:
            repo = ScheduledJobRepository(session)
            await repo.create(
                ScheduledJob(
                    organization_id=organization_id,
                    name="Job A",
                    job_type=JobType.CUSTOM_JOB,
                    status=ScheduledJobStatus.ACTIVE,
                )
            )
            await repo.create(
                ScheduledJob(
                    organization_id=other_organization_id,
                    name="Job B",
                    job_type=JobType.CUSTOM_JOB,
                    status=ScheduledJobStatus.ACTIVE,
                )
            )
            await session.commit()

        # Call #1 is the organizations lookup (must succeed to find both).
        # Call #2 is the first organization's own sweep session -- forced
        # to fail here. Call #3, the second organization's, is untouched.
        flaky = _flaky_after(db_session_factory, fail_on_call=2)
        worker = StatisticsWorker(flaky)  # type: ignore[arg-type]
        done = await worker.tick()
        assert done == 1


class TestMaintenanceSweepWorker:
    async def test_tick_announces_a_recently_started_window(
        self,
        db_session_factory: async_sessionmaker[AsyncSession],
        maintenance_repo,
        organization_id,
        publisher: RecordingPublisher,
    ) -> None:
        now = datetime.now(UTC)
        window = await maintenance_repo.create(
            MaintenanceWindow(
                organization_id=organization_id,
                title="Recently started",
                starts_at=now - timedelta(minutes=5),
                ends_at=now + timedelta(hours=2),
            )
        )
        worker = MaintenanceSweepWorker(
            db_session_factory, interval_seconds=3_600, publish_event=publisher
        )
        counts = await worker.tick()
        assert counts["started"] >= 1
        assert "MaintenanceStarted" in publisher.names
        started = next(e for e in publisher.events if e.event_name == "MaintenanceStarted")
        assert started.payload["window_id"] == str(window.id)

    async def test_tick_announces_a_recently_ended_window(
        self,
        db_session_factory: async_sessionmaker[AsyncSession],
        maintenance_repo,
        organization_id,
        publisher: RecordingPublisher,
    ) -> None:
        now = datetime.now(UTC)
        window = await maintenance_repo.create(
            MaintenanceWindow(
                organization_id=organization_id,
                title="Recently ended",
                starts_at=now - timedelta(hours=2),
                ends_at=now - timedelta(minutes=5),
            )
        )
        worker = MaintenanceSweepWorker(
            db_session_factory, interval_seconds=3_600, publish_event=publisher
        )
        counts = await worker.tick()
        assert counts["ended"] >= 1
        assert "MaintenanceEnded" in publisher.names
        ended = next(e for e in publisher.events if e.event_name == "MaintenanceEnded")
        assert ended.payload["window_id"] == str(window.id)

    async def test_a_window_outside_the_lookback_produces_neither(
        self,
        db_session_factory: async_sessionmaker[AsyncSession],
        maintenance_repo,
        organization_id,
        publisher: RecordingPublisher,
    ) -> None:
        now = datetime.now(UTC)
        await maintenance_repo.create(
            MaintenanceWindow(
                organization_id=organization_id,
                title="Long over",
                starts_at=now - timedelta(days=10),
                ends_at=now - timedelta(days=9),
            )
        )
        worker = MaintenanceSweepWorker(
            db_session_factory, interval_seconds=3_600, publish_event=publisher
        )
        counts = await worker.tick()
        assert counts["started"] == 0
        assert counts["ended"] == 0
        assert publisher.events == []

    async def test_run_job_delegates_to_tick(
        self, db_session_factory: async_sessionmaker[AsyncSession]
    ) -> None:
        worker = MaintenanceSweepWorker(db_session_factory)
        await worker.run_job(None)  # type: ignore[arg-type]

    async def test_a_tick_with_no_organizations_reports_all_zero(
        self, db_session_factory: async_sessionmaker[AsyncSession]
    ) -> None:
        worker = MaintenanceSweepWorker(db_session_factory, max_per_tick=0)
        counts = await worker.tick()
        assert counts == {"organizations": 0, "started": 0, "ended": 0}
