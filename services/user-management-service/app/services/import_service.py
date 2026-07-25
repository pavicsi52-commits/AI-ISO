"""Bulk user import.

Per docs/031 "IMPORT": CSV, Excel, JSON, Bulk Import, Validation,
Duplicate Detection, Error Report, Preview, Rollback. Per
"PERFORMANCE": "Background Import" -- :meth:`UserImportService.create_job`
only uploads the file and enqueues a job (fast, request-scoped);
:meth:`UserImportService.process_job` does the actual parsing/
validation/row-creation and is what a queue consumer
(:mod:`app.workers.import_worker`) calls.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from shared_core.enums.job_status import JobStatus
from shared_core.events.base import DomainEvent
from shared_core.exceptions.conflict import ConflictError
from shared_core.storage import StorageWrapper

from app.constants import DEFAULT_ORGANIZATION_ID
from app.events.user_events import UserImportedEvent
from app.models.enums import ActivityType, ImportFormat, UserStatus
from app.models.import_job import UserImportJob
from app.parsers import parse_csv_rows, parse_excel_rows, parse_json_rows
from app.repositories.import_job import UserImportJobRepository
from app.services.activity import UserActivityService
from app.services.user import UserService

EventPublisher = Callable[[DomainEvent], Awaitable[None]]

_REQUIRED_FIELDS = ("username", "email")
_PARSERS = {
    ImportFormat.CSV: parse_csv_rows,
    ImportFormat.EXCEL: parse_excel_rows,
    ImportFormat.JSON: parse_json_rows,
}


class UserImportService:
    """Uploads, processes, previews, and rolls back bulk user-import jobs."""

    def __init__(
        self,
        jobs: UserImportJobRepository,
        users: UserService,
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
        self,
        requested_by: UUID,
        *,
        source_format: ImportFormat,
        filename: str,
        content: bytes,
        preview_only: bool,
    ) -> UserImportJob:
        """Upload *content* and queue a bulk import job ("Bulk Import")."""
        await self._storage.ensure_bucket(self._bucket)
        storage_key = f"imports/{requested_by}/{datetime.now(UTC).timestamp()}_{filename}"
        content_type = "application/octet-stream"
        await self._storage.upload(self._bucket, storage_key, content, content_type)
        return await self._jobs.create(
            UserImportJob(
                requested_by=requested_by,
                source_format=source_format,
                source_storage_key=storage_key,
                preview_only=preview_only,
                status=JobStatus.QUEUED,
                organization_id=DEFAULT_ORGANIZATION_ID,
            )
        )

    async def get_job(self, job_id: UUID) -> UserImportJob:
        """Return one import job by id.

        Raises:
            NotFoundError: If no such job exists.
        """
        return await self._jobs.require_by_id(job_id)

    async def process_job(self, job_id: UUID) -> UserImportJob:
        """Download, parse, validate, and (unless previewing) create users for *job_id*.

        Raises:
            ConflictError: If *job_id* isn't in a processable state.
        """
        job = await self._jobs.require_by_id(job_id)
        if job.status not in (JobStatus.QUEUED, JobStatus.PENDING):
            raise ConflictError(f"Import job '{job_id}' is not queued for processing.")

        job.status = JobStatus.RUNNING
        job.started_at = datetime.now(UTC)
        content = await self._storage.download(self._bucket, job.source_storage_key)
        rows = _PARSERS[job.source_format](content)
        job.total_rows = len(rows)

        seen_usernames: set[str] = set()
        seen_emails: set[str] = set()
        errors: list[dict[str, Any]] = []
        created_ids: list[str] = []

        for index, row in enumerate(rows):
            job.processed_rows += 1
            missing = [field for field in _REQUIRED_FIELDS if not row.get(field)]
            if missing:
                job.failed_rows += 1
                errors.append({"row": index, "error": f"Missing required fields: {missing}"})
                continue
            username, email = row["username"], row["email"]
            if username in seen_usernames or email in seen_emails:
                job.duplicate_rows += 1
                errors.append({"row": index, "error": "Duplicate within import file"})
                continue
            seen_usernames.add(username)
            seen_emails.add(email)

            if job.preview_only:
                job.succeeded_rows += 1
                continue
            try:
                user = await self._users.create(
                    username=username,
                    email=email,
                    display_name=row.get("display_name") or None,
                    first_name=row.get("first_name") or None,
                    middle_name=row.get("middle_name") or None,
                    last_name=row.get("last_name") or None,
                    phone_number=row.get("phone_number") or None,
                    timezone=row.get("timezone") or "UTC",
                    language=row.get("language") or "en",
                    locale=row.get("locale") or "en-US",
                    status=UserStatus.PENDING,
                )
                created_ids.append(str(user.id))
                job.succeeded_rows += 1
            except ConflictError as exc:
                job.failed_rows += 1
                errors.append({"row": index, "error": str(exc)})

        job.error_report = errors
        job.created_user_ids = created_ids
        job.status = JobStatus.COMPLETED
        job.completed_at = datetime.now(UTC)
        await self._activity.record(job.requested_by, activity_type=ActivityType.IMPORTED)
        await self._publish(
            UserImportedEvent(
                source_service="user-management-service",
                payload={"job_id": str(job.id), "succeeded_rows": job.succeeded_rows},
            )
        )
        return job

    async def rollback_job(self, job_id: UUID) -> UserImportJob:
        """Soft-delete every user *job_id* created ("Rollback").

        Raises:
            ConflictError: If *job_id* was never completed, or was preview-only.
        """
        job = await self._jobs.require_by_id(job_id)
        if job.status != JobStatus.COMPLETED or job.preview_only:
            raise ConflictError(f"Import job '{job_id}' has nothing to roll back.")
        for raw_user_id in job.created_user_ids:
            user = await self._users.get_by_id(UUID(raw_user_id))
            if user is not None:
                await self._users.delete(user)
        job.rolled_back_at = datetime.now(UTC)
        return job


__all__ = ["UserImportService"]
