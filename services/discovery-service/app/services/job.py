"""Discovery job lifecycle management. ``create_job()`` only creates the
job row and commits immediately (see the module-level note below); the
actual scan execution is
``app/services/discovery_execution.py::DiscoveryExecutionService
.run_job()``, invoked by ``app/workers/discovery_worker.py`` off a queue
message -- the same "fast, request-scoped create; slow, queue-consumed
execute" split ``services/inventory-service``'s own
``AssetImportService`` established.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from datetime import UTC, datetime
from uuid import UUID

from shared_core.enums.job_status import JobStatus
from shared_core.events.base import DomainEvent
from shared_core.exceptions.conflict import ConflictError
from sqlalchemy.ext.asyncio import AsyncSession

from app.events.discovery_events import DiscoveryCancelledEvent
from app.models.discovery_job import DiscoveryJob
from app.models.enums import DiscoveryMode
from app.repositories.discovery_job import DiscoveryJobRepository
from app.repositories.discovery_target import DiscoveryTargetRepository

EventPublisher = Callable[[DomainEvent], Awaitable[None]]
_SOURCE_SERVICE = "discovery-service"


class DiscoveryJobService:
    """Creates, reads, and cancels discovery jobs."""

    def __init__(
        self,
        jobs: DiscoveryJobRepository,
        targets: DiscoveryTargetRepository,
        session: AsyncSession,
        publish_event: EventPublisher | None = None,
    ) -> None:
        self._jobs = jobs
        self._targets = targets
        self._session = session
        self._publish_event = publish_event

    async def _publish(self, event: DomainEvent) -> None:
        if self._publish_event is not None:
            await self._publish_event(event)

    async def get_by_id(self, job_id: UUID) -> DiscoveryJob:
        """Return the job identified by *job_id*.

        Raises:
            NotFoundError: If no such job exists.
        """
        return await self._jobs.require_by_id(job_id)

    async def list_for_org(self, organization_id: UUID) -> list[DiscoveryJob]:
        """Every discovery job for *organization_id*."""
        return await self._jobs.list_for_org(organization_id)

    async def create_job(
        self,
        *,
        organization_id: UUID,
        profile_id: UUID | None,
        mode: DiscoveryMode,
        triggered_by: UUID | None,
        schedule_id: UUID | None = None,
    ) -> DiscoveryJob:
        """Queue a new discovery job against *profile_id*'s currently
        registered targets.

        Commits immediately after creating the job row -- the request
        handler (or the scheduler's own trigger callback) publishes to
        the queue right after this returns, and the in-process worker
        consuming it uses a *different* database session/connection. A
        same-process RabbitMQ round trip can be fast enough that the
        worker's own read arrives before this request's own
        ``session_scope`` dependency teardown would otherwise have
        committed, producing a real, deterministic ``NotFoundError`` --
        the exact bug class ``services/project-service``'s own
        ``ProjectImportService.create_job`` was caught making live,
        fixed the same way here proactively.
        """
        total_targets = 0
        if profile_id is not None:
            total_targets = len(await self._targets.list_for_profile(profile_id))
        job = await self._jobs.create(
            DiscoveryJob(
                organization_id=organization_id,
                profile_id=profile_id,
                schedule_id=schedule_id,
                mode=mode,
                status=JobStatus.QUEUED,
                triggered_by=triggered_by,
                total_targets=total_targets,
            )
        )
        await self._session.commit()
        return job

    async def cancel(self, job_id: UUID) -> DiscoveryJob:
        """Cancel a queued or running job.

        Raises:
            ConflictError: If *job_id* has already finished.
        """
        job = await self.get_by_id(job_id)
        if job.status in (JobStatus.COMPLETED, JobStatus.FAILED, JobStatus.CANCELLED):
            raise ConflictError(f"Discovery job '{job_id}' has already finished.")
        job.status = JobStatus.CANCELLED
        job.completed_at = datetime.now(UTC)
        await self._publish(
            DiscoveryCancelledEvent(
                source_service=_SOURCE_SERVICE,
                organization_id=job.organization_id,
                payload={"job_id": str(job.id)},
            )
        )
        return job


__all__ = ["DiscoveryJobService"]
