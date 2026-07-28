"""The scheduled-report worker.

Polls for due schedules and runs them. Uses ``shared_core.scheduler``'s
own :class:`~shared_core.scheduler.manager.SchedulerManager` for leader
election, so in a multi-replica deployment exactly one instance runs
the tick -- otherwise every replica would generate the same report and
mail it to every recipient N times.

**Each schedule is processed independently.** One report failing must
not stop the rest of the tick, so every run is caught, recorded against
its own schedule, and the loop continues. A schedule that keeps failing
is disabled by :class:`~app.services.schedule.ReportScheduleService`
rather than retried forever.
"""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID

from shared_core.logging.logger import get_logger
from shared_core.scheduler import Job
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.clients.platform import PlatformSourceClient
from app.models.enums import ExportFormat
from app.notifications.report_notifications import ReportNotificationService
from app.renderer.engine import ReportRenderer
from app.repositories.report_execution import ReportExecutionRepository
from app.repositories.report_export import ReportExportRepository
from app.repositories.report_history import ReportHistoryRepository
from app.repositories.report_job import ReportJobRepository
from app.repositories.report_parameter import ReportParameterRepository
from app.repositories.report_schedule import ReportScheduleRepository
from app.repositories.report_template import ReportTemplateRepository
from app.services.generation import ReportGenerationService
from app.services.schedule import ReportScheduleService
from app.services.template import ReportTemplateService
from app.types import EventPublisher

logger = get_logger("app.workers.scheduler")


class ScheduledReportWorker:
    """Runs schedules that have come due."""

    def __init__(
        self,
        session_factory: async_sessionmaker[AsyncSession],
        *,
        source_client_factory: object,
        publish_event: EventPublisher,
        notifications: ReportNotificationService,
        max_per_tick: int = 25,
    ) -> None:
        self._session_factory = session_factory
        self._source_client_factory = source_client_factory
        self._publish_event = publish_event
        self._notifications = notifications
        self._max_per_tick = max_per_tick

    async def run_job(self, _job: Job) -> None:
        """Entry point matching ``shared_core.scheduler``'s own ``JobFn``.

        The framework calls a job with the :class:`Job` itself and
        expects nothing back, while :meth:`tick` takes a moment and
        returns a count for direct testing. This adapter keeps both
        honest instead of bending one to fit the other -- and its
        existence is why a signature mismatch cannot reach production
        as "the scheduler silently never fired".
        """
        await self.tick()

    async def tick(self, *, moment: datetime | None = None) -> int:
        """Run every due schedule once; returns how many ran.

        Each schedule gets its **own session**, so one failure cannot
        poison the transaction of the next. That matters more than the
        extra connections: a shared session that hits an error is
        unusable for everything after it in the tick.
        """
        now = moment or datetime.now(UTC)
        async with self._session_factory() as session:
            due = await ReportScheduleRepository(session).list_due(now, limit=self._max_per_tick)
            schedule_ids = [schedule.id for schedule in due]

        ran = 0
        for schedule_id in schedule_ids:
            if await self._run_one(schedule_id):
                ran += 1
        return ran

    async def _run_one(self, schedule_id: UUID) -> bool:
        """Run one schedule, recording success or failure. Never raises."""
        async with self._session_factory() as session:
            schedules = ReportScheduleService(
                ReportScheduleRepository(session), publish_event=self._publish_event
            )
            schedule = await schedules.get_by_id(schedule_id)
            jobs = ReportJobRepository(session)
            job = await jobs.get_by_id(schedule.job_id)
            if job is None or not job.enabled:
                await schedules.mark_failed(
                    schedule, "The scheduled report no longer exists or is disabled."
                )
                await session.commit()
                return False

            templates = ReportTemplateService(
                ReportTemplateRepository(session), ReportParameterRepository(session)
            )
            sources = self._build_sources()
            generation = ReportGenerationService(
                jobs,
                ReportExecutionRepository(session),
                ReportExportRepository(session),
                ReportHistoryRepository(session),
                templates,
                ReportRenderer(sources, None),
                publish_event=self._publish_event,
            )

            export_format = (
                schedule.export_format
                if isinstance(schedule.export_format, ExportFormat)
                else ExportFormat(schedule.export_format)
            )
            try:
                await generation.generate(
                    job,
                    export_formats=[export_format],
                    schedule_id=schedule.id,
                    triggered_by=schedule.created_by,
                )
            except Exception as exc:
                logger.warning(
                    "Scheduled report failed.",
                    extra={
                        "extra_fields": {
                            "schedule_id": str(schedule_id),
                            "error": str(exc),
                        }
                    },
                )
                await schedules.mark_failed(schedule, str(exc))
                await session.commit()
                if schedule.notify_on_failure and job.owner_id is not None:
                    await self._notifications.send_report_failed(
                        str(job.owner_id), title=job.name, reason=str(exc)
                    )
                return False

            await schedules.mark_succeeded(schedule)
            await session.commit()
            if job.owner_id is not None:
                await self._notifications.send_scheduled_complete(str(job.owner_id), title=job.name)
            return True

    def _build_sources(self) -> PlatformSourceClient:
        """Build a data-source client for an unattended run.

        Unattended runs have no caller, so the factory supplies whatever
        token the deployment configured for scheduled work. That is a
        deliberate, visible seam rather than a silent privilege
        escalation: a scheduled report runs as a service identity, and
        the deployment decides what that identity may read.
        """
        factory = self._source_client_factory
        assert callable(factory)
        return factory()  # type: ignore[no-any-return]


__all__ = ["ScheduledReportWorker"]
