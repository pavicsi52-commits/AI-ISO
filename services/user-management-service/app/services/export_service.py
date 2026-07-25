"""Bulk user export.

Per docs/031 "EXPORT": CSV, Excel, JSON, PDF, Filtered Export,
Background Processing, Audit. Per "PERFORMANCE": "Background Export" --
:meth:`UserExportService.create_job` only creates the job row (fast,
request-scoped); :meth:`UserExportService.process_job` queries and
serializes the full result set and is what a queue consumer
(:mod:`app.workers.export_worker`) calls.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from shared_core.database.filtering import Filter, FilterOperator
from shared_core.enums.job_status import JobStatus
from shared_core.events.base import DomainEvent
from shared_core.exceptions.conflict import ConflictError
from shared_core.storage import StorageWrapper

from app.constants import DEFAULT_ORGANIZATION_ID
from app.events.user_events import UserExportedEvent
from app.models.enums import ActivityType, ExportFormat
from app.models.export_job import UserExportJob
from app.parsers import write_csv_rows, write_excel_rows, write_json_rows, write_pdf_rows
from app.repositories.export_job import UserExportJobRepository
from app.repositories.user import UserRepository
from app.services.activity import UserActivityService

EventPublisher = Callable[[DomainEvent], Awaitable[None]]

_EXPORT_FIELDS = (
    "id",
    "username",
    "email",
    "display_name",
    "status",
    "created_at",
)
_RowWriter = Callable[[list[dict[str, Any]]], bytes]
_WRITERS: dict[ExportFormat, _RowWriter] = {
    ExportFormat.CSV: lambda rows: write_csv_rows(rows, list(_EXPORT_FIELDS)),
    ExportFormat.EXCEL: lambda rows: write_excel_rows(rows, list(_EXPORT_FIELDS)),
    ExportFormat.JSON: write_json_rows,
    ExportFormat.PDF: lambda rows: write_pdf_rows(rows, list(_EXPORT_FIELDS)),
}
_EXTENSIONS = {
    ExportFormat.CSV: "csv",
    ExportFormat.EXCEL: "xlsx",
    ExportFormat.JSON: "json",
    ExportFormat.PDF: "pdf",
}


class UserExportService:
    """Queues, processes, and serves the result of bulk user-export jobs."""

    def __init__(
        self,
        jobs: UserExportJobRepository,
        users: UserRepository,
        activity: UserActivityService,
        storage: StorageWrapper,
        *,
        bucket: str,
        publish_event: EventPublisher | None = None,
    ) -> None:
        self._jobs = jobs
        self._users = users
        self._activity = activity
        self._storage = storage
        self._bucket = bucket
        self._publish_event = publish_event

    async def _publish(self, event: DomainEvent) -> None:
        if self._publish_event is not None:
            await self._publish_event(event)

    async def create_job(
        self, requested_by: UUID, *, target_format: ExportFormat, filter_criteria: dict[str, Any]
    ) -> UserExportJob:
        """Queue a bulk export job ("Filtered Export"/"Background Processing")."""
        return await self._jobs.create(
            UserExportJob(
                requested_by=requested_by,
                target_format=target_format,
                filter_criteria=filter_criteria,
                status=JobStatus.QUEUED,
                organization_id=DEFAULT_ORGANIZATION_ID,
            )
        )

    async def get_job(self, job_id: UUID) -> UserExportJob:
        """Return one export job by id.

        Raises:
            NotFoundError: If no such job exists.
        """
        return await self._jobs.require_by_id(job_id)

    async def process_job(self, job_id: UUID) -> UserExportJob:
        """Query matching users and serialize them to *job_id*'s target format.

        Raises:
            ConflictError: If *job_id* isn't in a processable state.
        """
        job = await self._jobs.require_by_id(job_id)
        if job.status not in (JobStatus.QUEUED, JobStatus.PENDING):
            raise ConflictError(f"Export job '{job_id}' is not queued for processing.")

        job.status = JobStatus.RUNNING
        job.started_at = datetime.now(UTC)

        filters = [
            Filter(field, FilterOperator.EQUAL, value)
            for field, value in job.filter_criteria.items()
        ]
        result = await self._users.search_and_paginate(filters=filters, page=1, page_size=100_000)
        rows = [
            {
                "id": str(user.id),
                "username": user.username,
                "email": user.email,
                "display_name": user.display_name or "",
                "status": str(user.status),
                "created_at": user.created_at.isoformat(),
            }
            for user in result.items
        ]
        job.total_rows = len(rows)

        content = _WRITERS[job.target_format](rows)
        await self._storage.ensure_bucket(self._bucket)
        extension = _EXTENSIONS[job.target_format]
        storage_key = f"exports/{job.requested_by}/{job.id}.{extension}"
        content_type = "application/octet-stream"
        await self._storage.upload(self._bucket, storage_key, content, content_type)

        job.result_storage_key = storage_key
        job.status = JobStatus.COMPLETED
        job.completed_at = datetime.now(UTC)
        await self._activity.record(job.requested_by, activity_type=ActivityType.EXPORTED)
        await self._publish(
            UserExportedEvent(
                source_service="user-management-service",
                payload={"job_id": str(job.id), "total_rows": job.total_rows},
            )
        )
        return job

    async def download_url(self, job: UserExportJob, *, expires_seconds: int = 3600) -> str | None:
        """A time-limited download URL for *job*'s result file, if it's ready."""
        if job.result_storage_key is None:
            return None
        return await self._storage.presigned_url(
            self._bucket, job.result_storage_key, expires_seconds
        )


__all__ = ["UserExportService"]
