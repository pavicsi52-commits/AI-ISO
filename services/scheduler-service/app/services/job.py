"""Job creation, editing, and lifecycle.

A job is created directly ``ACTIVE`` -- eligible to be scheduled the
moment a trigger is attached -- rather than requiring a separate
"activate" call the docs/054 REST API surface does not list.
``REGISTERED`` remains a real, modeled status (a job briefly passes
through it within one ``create()`` call, recorded as its own
:class:`~app.models.history.JobHistory` row) so an audit trail always
shows the same two-step lineage every job actually has, not a status
that only ever appears synthetically.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from shared_core.logging.logger import get_logger

from app.models.enums import JobPriority, JobType, ScheduledJobStatus
from app.models.history import JobHistory
from app.models.job import ScheduledJob
from app.repositories.history import JobHistoryRepository
from app.repositories.job import ScheduledJobRepository
from app.scheduling.engine import validate_job_transition
from app.types import EventPublisher

logger = get_logger("app.services.job")

_EDITABLE_FIELDS = frozenset(
    {
        "name",
        "description",
        "priority",
        "owner_id",
        "timezone",
        "payload",
        "job_metadata",
        "tags",
        "timeout_seconds",
    }
)


class JobService:
    """Jobs: creation, editing, and status lifecycle."""

    def __init__(
        self,
        jobs: ScheduledJobRepository,
        history: JobHistoryRepository,
        *,
        publish_event: EventPublisher | None = None,
    ) -> None:
        self._jobs = jobs
        self._history = history
        self._publish = publish_event

    async def _publish_event(self, event: Any) -> None:
        if self._publish is not None:
            await self._publish(event)

    async def _record_history(
        self,
        organization_id: UUID,
        job_id: UUID,
        *,
        from_status: ScheduledJobStatus | None,
        to_status: ScheduledJobStatus,
        actor_id: str | None,
        note: str | None = None,
    ) -> None:
        await self._history.create(
            JobHistory(
                organization_id=organization_id,
                job_id=job_id,
                from_status=str(from_status) if from_status else None,
                to_status=str(to_status),
                occurred_at=datetime.now(UTC),
                actor_id=actor_id,
                note=note,
            )
        )

    async def create(
        self,
        organization_id: UUID,
        *,
        name: str,
        job_type: JobType,
        description: str | None = None,
        priority: JobPriority = JobPriority.NORMAL,
        owner_id: str | None = None,
        timezone: str = "UTC",
        payload: dict[str, Any] | None = None,
        job_metadata: dict[str, Any] | None = None,
        tags: list[str] | None = None,
        timeout_seconds: float | None = None,
        actor_id: str | None = None,
    ) -> ScheduledJob:
        """Register a new job, directly ``ACTIVE``."""
        created = await self._jobs.create(
            ScheduledJob(
                organization_id=organization_id,
                name=name,
                job_type=job_type,
                status=ScheduledJobStatus.ACTIVE,
                description=description,
                priority=priority,
                owner_id=owner_id,
                timezone=timezone,
                payload=dict(payload or {}),
                job_metadata=dict(job_metadata or {}),
                tags=list(tags or []),
                timeout_seconds=timeout_seconds,
                created_by=UUID(actor_id) if actor_id else None,
            )
        )
        await self._record_history(
            organization_id,
            created.id,
            from_status=None,
            to_status=ScheduledJobStatus.REGISTERED,
            actor_id=actor_id,
        )
        await self._record_history(
            organization_id,
            created.id,
            from_status=ScheduledJobStatus.REGISTERED,
            to_status=ScheduledJobStatus.ACTIVE,
            actor_id=actor_id,
        )
        return created

    async def get(self, organization_id: UUID, job_id: UUID) -> ScheduledJob:
        """One job.

        Raises:
            NotFoundError: If it does not exist here.
        """
        return await self._jobs.require_in_org(organization_id, job_id)

    async def list_jobs(
        self,
        organization_id: UUID,
        *,
        status: ScheduledJobStatus | None = None,
        job_type: JobType | None = None,
        priority: JobPriority | None = None,
        owner_id: str | None = None,
        limit: int = 200,
        offset: int = 0,
    ) -> list[ScheduledJob]:
        """Jobs matching a caller's filters."""
        return await self._jobs.list_filtered(
            organization_id,
            status=status,
            job_type=job_type,
            priority=priority,
            owner_id=owner_id,
            limit=limit,
            offset=offset,
        )

    async def update(
        self, organization_id: UUID, job_id: UUID, *, actor_id: str | None = None, **fields: Any
    ) -> ScheduledJob:
        """Edit a job's own editable fields.

        Silently ignores any key in *fields* outside
        :data:`_EDITABLE_FIELDS` (e.g. ``status``, ``job_type``) --
        those change only through the dedicated lifecycle methods below,
        which is what keeps history/events honest about *why* they
        changed.
        """
        stored = await self._jobs.require_in_org(organization_id, job_id)
        for field, value in fields.items():
            if field in _EDITABLE_FIELDS:
                setattr(stored, field, value)
        stored.updated_by = UUID(actor_id) if actor_id else None
        return await self._jobs.update(stored)

    async def pause(
        self, organization_id: UUID, job_id: UUID, *, actor_id: str | None = None
    ) -> ScheduledJob:
        """Pause a job -- temporarily, resumable via :meth:`resume`.

        Raises:
            ValidationError: If the job is not currently ``ACTIVE``.
        """
        moment = datetime.now(UTC)
        stored = await self._jobs.require_in_org(organization_id, job_id)
        current = ScheduledJobStatus(stored.status)
        validate_job_transition(current, ScheduledJobStatus.PAUSED)
        stored.status = ScheduledJobStatus.PAUSED
        stored.paused_at = moment
        stored.updated_by = UUID(actor_id) if actor_id else None
        updated = await self._jobs.update(stored)
        await self._record_history(
            organization_id,
            job_id,
            from_status=current,
            to_status=ScheduledJobStatus.PAUSED,
            actor_id=actor_id,
        )
        return updated

    async def resume(
        self, organization_id: UUID, job_id: UUID, *, actor_id: str | None = None
    ) -> ScheduledJob:
        """Resume a paused job.

        Raises:
            ValidationError: If the job is not currently ``PAUSED``.
        """
        stored = await self._jobs.require_in_org(organization_id, job_id)
        current = ScheduledJobStatus(stored.status)
        validate_job_transition(current, ScheduledJobStatus.ACTIVE)
        stored.status = ScheduledJobStatus.ACTIVE
        stored.paused_at = None
        stored.updated_by = UUID(actor_id) if actor_id else None
        updated = await self._jobs.update(stored)
        await self._record_history(
            organization_id,
            job_id,
            from_status=current,
            to_status=ScheduledJobStatus.ACTIVE,
            actor_id=actor_id,
        )
        return updated

    async def cancel(
        self,
        organization_id: UUID,
        job_id: UUID,
        *,
        actor_id: str | None = None,
        reason: str | None = None,
    ) -> ScheduledJob:
        """Stop a job for good, short of deleting it -- disabled, not resumable via :meth:`resume`.

        Raises:
            ValidationError: If the job is already ``DISABLED`` or ``DELETED``.
        """
        stored = await self._jobs.require_in_org(organization_id, job_id)
        current = ScheduledJobStatus(stored.status)
        validate_job_transition(current, ScheduledJobStatus.DISABLED)
        stored.status = ScheduledJobStatus.DISABLED
        stored.disabled_at = datetime.now(UTC)
        stored.updated_by = UUID(actor_id) if actor_id else None
        updated = await self._jobs.update(stored)
        await self._record_history(
            organization_id,
            job_id,
            from_status=current,
            to_status=ScheduledJobStatus.DISABLED,
            actor_id=actor_id,
            note=reason,
        )
        return updated

    async def delete(
        self, organization_id: UUID, job_id: UUID, *, actor_id: str | None = None
    ) -> ScheduledJob:
        """Delete a job for good.

        Raises:
            ValidationError: If the job is already ``DELETED``.
        """
        stored = await self._jobs.require_in_org(organization_id, job_id)
        current = ScheduledJobStatus(stored.status)
        validate_job_transition(current, ScheduledJobStatus.DELETED)
        stored.status = ScheduledJobStatus.DELETED
        stored.updated_by = UUID(actor_id) if actor_id else None
        updated = await self._jobs.update(stored)
        await self._record_history(
            organization_id,
            job_id,
            from_status=current,
            to_status=ScheduledJobStatus.DELETED,
            actor_id=actor_id,
        )
        return updated

    async def record_run(self, organization_id: UUID, job_id: UUID, *, ran_at: datetime) -> None:
        """Update a job's own denormalised ``last_run_at``/counters after one execution.

        Deliberately does not touch ``status`` -- a job stays ``ACTIVE``
        (or whatever it already was) across any number of runs; only
        the lifecycle methods above change status.
        """
        stored = await self._jobs.require_in_org(organization_id, job_id)
        stored.last_run_at = ran_at
        stored.run_count += 1
        await self._jobs.update(stored)

    async def record_failure(self, organization_id: UUID, job_id: UUID) -> None:
        """Increment a job's own denormalised failure counter."""
        stored = await self._jobs.require_in_org(organization_id, job_id)
        stored.failure_count += 1
        await self._jobs.update(stored)


__all__ = ["JobService"]
