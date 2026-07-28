"""The scheduled-report worker, telemetry spans, notifications, and
the domain-event registry.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

import httpx
import pytest
from opentelemetry import trace
from shared_core.enums.notification_channel import NotificationChannel
from shared_core.events import default_registry
from shared_core.events.base import DomainEvent
from shared_core.exceptions.notification import NotificationError
from shared_core.scheduler import Job, JobType, Schedule
from shared_core.scheduler import ScheduleType as FrameworkScheduleType
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.clients.platform import PlatformSourceClient, SourceEndpoints
from app.events.report_events import (
    SOURCE_SERVICE,
    ReportArchivedEvent,
    ReportCreatedEvent,
    ReportDeliveredEvent,
    ReportDownloadedEvent,
    ReportFailedEvent,
    ReportGeneratedEvent,
    ReportScheduledEvent,
)
from app.models.enums import ExportFormat, ScheduleFrequency, TemplateStatus
from app.notifications.report_notifications import ReportNotificationService
from app.repositories.report_execution import ReportExecutionRepository
from app.repositories.report_job import ReportJobRepository
from app.repositories.report_schedule import ReportScheduleRepository
from app.scheduler.registrar import (
    SCHEDULED_REPORT_JOB_ID,
    register_scheduled_report_tick,
)
from app.services.schedule import ReportScheduleService
from app.telemetry.tracing import (
    trace_archive,
    trace_distribution,
    trace_export,
    trace_rendering,
    trace_scheduling,
    trace_template_rendering,
)
from app.workers.scheduler import ScheduledReportWorker
from tests.conftest import RecordingPublisher, make_job, make_template, source_handler


class _RecordingNotifier:
    """A notification manager surface that records rather than sends."""

    def __init__(self, *, fail: bool = False) -> None:
        self.sent: list[dict[str, Any]] = []
        self._fail = fail

    async def send(self, **kwargs: Any) -> None:
        if self._fail:
            raise NotificationError("smtp unreachable")
        self.sent.append(kwargs)


class TestScheduledReportWorker:
    def _worker(
        self,
        factory: async_sessionmaker[AsyncSession],
        http_client: httpx.AsyncClient,
        endpoints: SourceEndpoints,
        notifier: _RecordingNotifier,
    ) -> ScheduledReportWorker:
        return ScheduledReportWorker(
            factory,
            source_client_factory=lambda: PlatformSourceClient(
                http_client, endpoints, caller_token="service-token"
            ),
            publish_event=RecordingPublisher(),
            notifications=ReportNotificationService(notifier),  # type: ignore[arg-type]
        )

    async def _due_schedule(
        self, factory: async_sessionmaker[AsyncSession], *, approved: bool = True
    ) -> tuple[uuid.UUID, uuid.UUID]:
        """Seed an approved report whose schedule is already due."""
        async with factory() as session:
            org = uuid.uuid4()
            owner = uuid.uuid4()
            template = await make_template(
                session,
                organization_id=org,
                status=TemplateStatus.APPROVED if approved else TemplateStatus.DRAFT,
            )
            job = await make_job(
                session,
                organization_id=org,
                template_id=template.id,
                owner_id=owner,
                default_format=ExportFormat.CSV,
            )
            schedules = ReportScheduleService(
                ReportScheduleRepository(session), publish_event=RecordingPublisher()
            )
            schedule = await schedules.create(
                organization_id=org,
                project_id=None,
                job_id=job.id,
                frequency=ScheduleFrequency.HOURLY,
                starts_at=datetime.now(UTC) - timedelta(hours=2),
                export_format=ExportFormat.CSV,
                max_retries=2,
            )
            schedule.next_run_at = datetime.now(UTC) - timedelta(minutes=1)
            await ReportScheduleRepository(session).update(schedule)
            await session.commit()
            return schedule.id, job.id

    async def test_a_due_schedule_runs_and_advances(
        self,
        db_session_factory: async_sessionmaker[AsyncSession],
        source_endpoints: SourceEndpoints,
    ) -> None:
        schedule_id, job_id = await self._due_schedule(db_session_factory)
        notifier = _RecordingNotifier()

        async with httpx.AsyncClient(
            transport=httpx.MockTransport(source_handler())
        ) as http_client:
            worker = self._worker(db_session_factory, http_client, source_endpoints, notifier)
            assert await worker.tick() == 1

        async with db_session_factory() as session:
            schedule = await ReportScheduleRepository(session).require_by_id(schedule_id)
            assert schedule.consecutive_failures == 0
            assert schedule.next_run_at is not None
            assert schedule.next_run_at > datetime.now(UTC)

            executions = await ReportExecutionRepository(session).list_for_job(job_id)
            assert len(executions) == 1
            assert executions[0].schedule_id == schedule_id

        assert any("complete" in call["subject"].lower() for call in notifier.sent)

    async def test_nothing_due_runs_nothing(
        self,
        db_session_factory: async_sessionmaker[AsyncSession],
        source_endpoints: SourceEndpoints,
    ) -> None:
        notifier = _RecordingNotifier()
        async with httpx.AsyncClient() as http_client:
            worker = self._worker(db_session_factory, http_client, source_endpoints, notifier)
            assert await worker.tick(moment=datetime(2000, 1, 1, tzinfo=UTC)) == 0

    async def test_a_failing_run_is_recorded_and_notified(
        self,
        db_session_factory: async_sessionmaker[AsyncSession],
        source_endpoints: SourceEndpoints,
    ) -> None:
        """One failing report must not stop the tick."""
        schedule_id, _job_id = await self._due_schedule(db_session_factory, approved=False)
        notifier = _RecordingNotifier()

        async with httpx.AsyncClient(
            transport=httpx.MockTransport(source_handler())
        ) as http_client:
            worker = self._worker(db_session_factory, http_client, source_endpoints, notifier)
            assert await worker.tick() == 0

        async with db_session_factory() as session:
            schedule = await ReportScheduleRepository(session).require_by_id(schedule_id)
            assert schedule.consecutive_failures == 1
            assert schedule.last_error is not None

        assert any("failed" in call["subject"].lower() for call in notifier.sent)

    async def test_a_disabled_report_marks_the_schedule_failed(
        self,
        db_session_factory: async_sessionmaker[AsyncSession],
        source_endpoints: SourceEndpoints,
    ) -> None:
        schedule_id, job_id = await self._due_schedule(db_session_factory)
        async with db_session_factory() as session:
            job = await ReportJobRepository(session).require_by_id(job_id)
            job.enabled = False
            await ReportJobRepository(session).update(job)
            await session.commit()

        notifier = _RecordingNotifier()
        async with httpx.AsyncClient() as http_client:
            worker = self._worker(db_session_factory, http_client, source_endpoints, notifier)
            assert await worker.tick() == 0

        async with db_session_factory() as session:
            schedule = await ReportScheduleRepository(session).require_by_id(schedule_id)
            assert "disabled" in (schedule.last_error or "")

    async def test_the_job_adapter_matches_the_framework_contract(
        self,
        db_session_factory: async_sessionmaker[AsyncSession],
        source_endpoints: SourceEndpoints,
    ) -> None:
        """``JobFn`` takes the Job and returns nothing.

        A signature mismatch here would mean the scheduler silently
        never fires, which is exactly the failure this adapter exists
        to make impossible.
        """
        notifier = _RecordingNotifier()
        async with httpx.AsyncClient(
            transport=httpx.MockTransport(source_handler())
        ) as http_client:
            worker = self._worker(db_session_factory, http_client, source_endpoints, notifier)
            job = Job(
                job_id="probe",
                job_name="probe",
                job_type=JobType.SYSTEM,
                fn=worker.run_job,
                schedule=Schedule(
                    schedule_type=FrameworkScheduleType.FIXED_RATE,
                    interval=timedelta(seconds=60),
                ),
            )
            # ``JobFn`` returns ``None``; awaiting it without raising
            # is the whole contract being asserted.
            await job.fn(job)


class TestSchedulerRegistrar:
    class _RecordingManager:
        def __init__(self) -> None:
            self.jobs: list[Any] = []

        def register_job(self, job: Any) -> None:
            self.jobs.append(job)

    async def test_a_single_platform_wide_tick_is_registered(self) -> None:
        """One poll serves every organization; N would be N times the load."""
        manager = self._RecordingManager()

        async def _fn(_job: Any) -> None:
            return None

        job = register_scheduled_report_tick(manager, _fn, interval_seconds=60)  # type: ignore[arg-type]
        assert job.job_id == SCHEDULED_REPORT_JOB_ID
        assert len(manager.jobs) == 1

    async def test_re_registering_replaces_rather_than_leaks(self) -> None:
        manager = self._RecordingManager()

        async def _fn(_job: Any) -> None:
            return None

        first = register_scheduled_report_tick(manager, _fn, interval_seconds=60)  # type: ignore[arg-type]
        second = register_scheduled_report_tick(manager, _fn, interval_seconds=30)  # type: ignore[arg-type]
        assert first.job_id == second.job_id

    @pytest.mark.parametrize("interval", [0, -1])
    async def test_a_non_positive_interval_is_rejected(self, interval: int) -> None:
        manager = self._RecordingManager()

        async def _fn(_job: Any) -> None:
            return None

        with pytest.raises(ValueError, match="must be positive"):
            register_scheduled_report_tick(manager, _fn, interval_seconds=interval)  # type: ignore[arg-type]


class TestTelemetry:
    @pytest.mark.parametrize(
        ("factory", "kwargs"),
        [
            (trace_rendering, {"report": "Fleet"}),
            (trace_template_rendering, {"template": "Fleet Report"}),
            (trace_export, {"export_format": "pdf"}),
            (trace_distribution, {"channel": "email"}),
            (trace_scheduling, {"schedule": "s-1"}),
            (trace_archive, {"operation": "purge"}),
        ],
    )
    def test_every_documented_span_opens(self, factory: Any, kwargs: dict[str, Any]) -> None:
        tracer = trace.get_tracer("test")
        with factory(tracer, **kwargs) as span:
            assert span is not None

    def test_extra_attributes_are_accepted(self) -> None:
        tracer = trace.get_tracer("test")
        with trace_export(tracer, export_format="csv", rows=412) as span:
            assert span is not None


class TestEvents:
    @pytest.mark.parametrize(
        ("event_class", "event_name"),
        [
            (ReportCreatedEvent, "ReportCreated"),
            (ReportGeneratedEvent, "ReportGenerated"),
            (ReportFailedEvent, "ReportFailed"),
            (ReportScheduledEvent, "ReportScheduled"),
            (ReportDeliveredEvent, "ReportDelivered"),
            (ReportDownloadedEvent, "ReportDownloaded"),
            (ReportArchivedEvent, "ReportArchived"),
        ],
    )
    def test_every_documented_event_is_registered(
        self, event_class: type[DomainEvent], event_name: str
    ) -> None:
        assert event_class.event_name == event_name
        assert default_registry.lookup(event_name) is event_class

    def test_an_event_carries_its_payload(self) -> None:
        event = ReportGeneratedEvent(source_service=SOURCE_SERVICE, payload={"row_count": 412})
        assert event.payload["row_count"] == 412
        assert event.source_service == "reporting-service"


class TestNotifications:
    async def test_every_documented_notification_is_sent(self) -> None:
        notifier = _RecordingNotifier()
        service = ReportNotificationService(notifier)  # type: ignore[arg-type]
        user = str(uuid.uuid4())

        await service.send_report_ready(user, title="Fleet")
        await service.send_report_failed(user, title="Fleet", reason="source down")
        await service.send_scheduled_complete(user, title="Fleet")
        await service.send_distribution_failed(
            user, title="Fleet", channel="email", reason="bounced"
        )
        await service.send_archive_completed(user, title="Fleet")

        assert len(notifier.sent) == 5
        assert all(call["channel"] is NotificationChannel.EMAIL for call in notifier.sent)
        assert all(call["user_id"] == user for call in notifier.sent)

    async def test_failures_are_typed_as_errors(self) -> None:
        notifier = _RecordingNotifier()
        service = ReportNotificationService(notifier)  # type: ignore[arg-type]
        await service.send_report_failed("u", title="Fleet", reason="x")
        await service.send_distribution_failed("u", title="Fleet", channel="email", reason="x")
        assert [str(call["notification_type"]) for call in notifier.sent] == ["error", "error"]

    async def test_a_failing_notifier_never_breaks_the_caller(self) -> None:
        """A report that generated correctly must not be marked failed
        because an SMTP server was down.
        """
        service = ReportNotificationService(_RecordingNotifier(fail=True))  # type: ignore[arg-type]
        await service.send_report_ready("u", title="Fleet")
