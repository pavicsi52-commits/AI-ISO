"""Bulk project import.

Per docs/034 "IMPORT": JSON, YAML, CSV, ZIP Package, Validation,
Preview, Conflict Detection, Rollback. Per "PERFORMANCE": "Background
Processing" -- :meth:`ProjectImportService.create_job` only uploads the
file and enqueues a job (fast, request-scoped);
:meth:`ProjectImportService.process_job` does the actual parsing/
validation/row-creation and is what a queue consumer
(:mod:`app.workers.import_worker`) calls. Mirrors
``services/user-management-service``'s identical
``UserImportService`` shape.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from shared_core.enums.job_status import JobStatus
from shared_core.exceptions.conflict import ConflictError
from shared_core.exceptions.validation import ValidationError
from shared_core.storage import StorageWrapper
from sqlalchemy.ext.asyncio import AsyncSession

from app.constants import DEFAULT_ORGANIZATION_ID
from app.models.enums import ImportFormat, ProjectPriority, ProjectVisibility
from app.models.project_import_job import ProjectImportJob
from app.parsers.csv_parser import parse_csv_rows
from app.parsers.json_parser import parse_json_rows
from app.parsers.yaml_parser import parse_yaml_rows
from app.parsers.zip_archive import extract_single_data_file
from app.repositories.project_import_job import ProjectImportJobRepository
from app.services.project import ProjectService

_REQUIRED_FIELDS = ("organization_id", "name", "code")


def _parse_rows(source_format: ImportFormat, content: bytes) -> list[dict[str, Any]]:
    if source_format == ImportFormat.JSON:
        return parse_json_rows(content)
    if source_format == ImportFormat.YAML:
        return parse_yaml_rows(content)
    if source_format == ImportFormat.CSV:
        return list(parse_csv_rows(content))
    filename, extracted = extract_single_data_file(content)
    if filename.lower().endswith((".yaml", ".yml")):
        return parse_yaml_rows(extracted)
    if filename.lower().endswith(".csv"):
        return list(parse_csv_rows(extracted))
    return parse_json_rows(extracted)


class ProjectImportService:
    """Uploads, processes, previews, and rolls back bulk project-import jobs."""

    def __init__(
        self,
        jobs: ProjectImportJobRepository,
        projects: ProjectService,
        storage: StorageWrapper,
        session: AsyncSession,
        *,
        bucket: str,
    ) -> None:
        self._jobs = jobs
        self._projects = projects
        self._storage = storage
        self._session = session
        self._bucket = bucket

    async def create_job(
        self,
        requested_by: UUID,
        *,
        source_format: ImportFormat,
        filename: str,
        content: bytes,
        preview_only: bool,
    ) -> ProjectImportJob:
        """Upload *content* and queue a bulk import job ("Bulk Import").

        Commits immediately after creating the job row -- the request
        handler publishes a queue message right after this returns, and
        the in-process worker consuming it uses a *different* database
        session/connection. A same-process RabbitMQ round trip can be
        fast enough that the worker's own read arrives before this
        request's own ``session_scope`` dependency teardown would
        otherwise have committed, causing a real, deterministic (not
        rare) ``NotFoundError`` -- caught live via smoke-testing, not
        theoretical. Every other write in this service can safely wait
        for the ordinary end-of-request commit; this one specifically
        hands its row to an independent consumer before that point.
        """
        await self._storage.ensure_bucket(self._bucket)
        storage_key = f"imports/{requested_by}/{datetime.now(UTC).timestamp()}_{filename}"
        await self._storage.upload(self._bucket, storage_key, content, "application/octet-stream")
        job = await self._jobs.create(
            ProjectImportJob(
                requested_by=requested_by,
                organization_id=DEFAULT_ORGANIZATION_ID,
                source_format=source_format,
                source_storage_key=storage_key,
                preview_only=preview_only,
                status=JobStatus.QUEUED,
            )
        )
        await self._session.commit()
        return job

    async def get_job(self, job_id: UUID) -> ProjectImportJob:
        """Return one import job by id.

        Raises:
            NotFoundError: If no such job exists.
        """
        return await self._jobs.require_by_id(job_id)

    async def process_job(self, job_id: UUID) -> ProjectImportJob:
        """Download, parse, validate, and (unless previewing) create projects
        for *job_id*.

        Raises:
            ConflictError: If *job_id* isn't in a processable state.
        """
        job = await self._jobs.require_by_id(job_id)
        if job.status not in (JobStatus.QUEUED, JobStatus.PENDING):
            raise ConflictError(f"Import job '{job_id}' is not queued for processing.")

        job.status = JobStatus.RUNNING
        job.started_at = datetime.now(UTC)
        content = await self._storage.download(self._bucket, job.source_storage_key)
        try:
            rows = _parse_rows(job.source_format, content)
        except ValidationError as exc:
            job.status = JobStatus.FAILED
            job.error_report = [{"row": None, "error": str(exc)}]
            job.completed_at = datetime.now(UTC)
            return job
        job.total_rows = len(rows)

        seen_codes: set[str] = set()
        errors: list[dict[str, Any]] = []
        created_ids: list[str] = []

        for index, row in enumerate(rows):
            job.processed_rows += 1
            missing = [field for field in _REQUIRED_FIELDS if not row.get(field)]
            if missing:
                job.failed_rows += 1
                errors.append({"row": index, "error": f"Missing required fields: {missing}"})
                continue
            code = str(row["code"])
            if code in seen_codes:
                job.duplicate_rows += 1
                errors.append({"row": index, "error": "Duplicate code within import file"})
                continue
            seen_codes.add(code)

            if job.preview_only:
                job.succeeded_rows += 1
                continue
            try:
                project = await self._projects.create(
                    organization_id=UUID(str(row["organization_id"])),
                    owner_id=job.requested_by,
                    name=str(row["name"]),
                    code=code,
                    display_name=row.get("display_name") or None,
                    description=row.get("description") or None,
                    visibility=ProjectVisibility(row.get("visibility") or "private"),
                    default_language=row.get("default_language") or "en",
                    timezone=row.get("timezone") or "UTC",
                    category=row.get("category") or None,
                    priority=ProjectPriority(row.get("priority") or "medium"),
                    metadata=row.get("metadata") or {},
                )
                created_ids.append(str(project.id))
                job.succeeded_rows += 1
            except (ConflictError, ValueError) as exc:
                job.failed_rows += 1
                errors.append({"row": index, "error": str(exc)})

        job.error_report = errors
        job.created_project_ids = created_ids
        job.status = JobStatus.COMPLETED
        job.completed_at = datetime.now(UTC)
        # Each created project already recorded its own PROJECT_CREATED
        # activity entry inside ProjectService.create() -- a bulk import
        # spans potentially many projects, so there is no single project
        # to attach one more "imported" entry to.
        return job

    async def rollback_job(self, job_id: UUID) -> ProjectImportJob:
        """Soft-delete every project *job_id* created ("Rollback").

        Raises:
            ConflictError: If *job_id* was never completed, or was preview-only.
        """
        job = await self._jobs.require_by_id(job_id)
        if job.status != JobStatus.COMPLETED or job.preview_only:
            raise ConflictError(f"Import job '{job_id}' has nothing to roll back.")
        for raw_project_id in job.created_project_ids:
            await self._projects.delete(UUID(raw_project_id))
        job.rolled_back_at = datetime.now(UTC)
        return job


__all__ = ["ProjectImportService"]
