"""Bulk project export.

Per docs/034 "EXPORT": JSON, YAML, ZIP Package, PDF Summary, Background
Processing, Audit Logging. Mirrors
``services/user-management-service``'s identical ``UserExportService``
shape.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from shared_core.enums.job_status import JobStatus
from shared_core.exceptions.conflict import ConflictError
from shared_core.storage import StorageWrapper
from sqlalchemy.ext.asyncio import AsyncSession

from app.constants import DEFAULT_ORGANIZATION_ID
from app.models.enums import ExportFormat, ProjectStatus
from app.models.project_export_job import ProjectExportJob
from app.parsers.csv_parser import write_csv_rows
from app.parsers.json_parser import write_json_rows
from app.parsers.pdf_writer import write_pdf_summary
from app.parsers.yaml_parser import write_yaml_rows
from app.parsers.zip_archive import build_export_package
from app.repositories.project import ProjectRepository
from app.repositories.project_export_job import ProjectExportJobRepository
from app.repositories.project_tag import ProjectTagRepository

_FIELDNAMES = [
    "id",
    "organization_id",
    "name",
    "code",
    "display_name",
    "description",
    "status",
    "owner_id",
    "visibility",
    "category",
    "priority",
    "created_at",
]


class ProjectExportService:
    """Requests, processes, and reports on bulk project-export jobs."""

    def __init__(
        self,
        jobs: ProjectExportJobRepository,
        projects: ProjectRepository,
        tags: ProjectTagRepository,
        storage: StorageWrapper,
        session: AsyncSession,
        *,
        bucket: str,
    ) -> None:
        self._jobs = jobs
        self._projects = projects
        self._tags = tags
        self._storage = storage
        self._session = session
        self._bucket = bucket

    async def create_job(
        self,
        requested_by: UUID,
        *,
        target_format: ExportFormat,
        filter_criteria: dict[str, Any],
    ) -> ProjectExportJob:
        """Queue a bulk export job ("Background Processing").

        Commits immediately -- see
        ``app/services/import_service.py::ProjectImportService.create_job``'s
        docstring for why a job about to be handed to an independent
        queue-consumer worker can't wait for the ordinary end-of-request
        commit.
        """
        job = await self._jobs.create(
            ProjectExportJob(
                requested_by=requested_by,
                organization_id=DEFAULT_ORGANIZATION_ID,
                target_format=target_format,
                filter_criteria=filter_criteria,
                status=JobStatus.QUEUED,
            )
        )
        await self._session.commit()
        return job

    async def get_job(self, job_id: UUID) -> ProjectExportJob:
        """Return one export job by id.

        Raises:
            NotFoundError: If no such job exists.
        """
        return await self._jobs.require_by_id(job_id)

    async def download_url(
        self, job: ProjectExportJob, *, expires_seconds: int = 3600
    ) -> str | None:
        """A presigned, time-limited download URL for a completed job's
        result, or ``None`` if the job hasn't produced one yet.
        """
        if job.result_storage_key is None:
            return None
        return await self._storage.presigned_url(
            self._bucket, job.result_storage_key, expires_seconds
        )

    async def process_job(self, job_id: UUID) -> ProjectExportJob:
        """Query, serialize, and upload the result for *job_id* ("Audit Logging").

        Raises:
            ConflictError: If *job_id* isn't in a processable state.
        """
        job = await self._jobs.require_by_id(job_id)
        if job.status not in (JobStatus.QUEUED, JobStatus.PENDING):
            raise ConflictError(f"Export job '{job_id}' is not queued for processing.")

        job.status = JobStatus.RUNNING
        job.started_at = datetime.now(UTC)

        organization_id = UUID(str(job.filter_criteria["organization_id"]))
        status = job.filter_criteria.get("status")
        category = job.filter_criteria.get("category")
        tag_labels: list[str] = job.filter_criteria.get("tags") or []

        projects = await self._projects.list_filtered(
            organization_id,
            status=ProjectStatus(status) if status else None,
            category=category,
        )
        if tag_labels:
            tagged_project_ids = await self._tags.list_project_ids_for_labels(
                organization_id, tag_labels
            )
            projects = [p for p in projects if p.id in tagged_project_ids]

        rows = [
            {
                "id": str(p.id),
                "organization_id": str(p.organization_id),
                "name": p.name,
                "code": p.code,
                "display_name": p.display_name,
                "description": p.description,
                "status": str(p.status),
                "owner_id": str(p.owner_id),
                "visibility": str(p.visibility),
                "category": p.category,
                "priority": str(p.priority),
                "created_at": p.created_at.isoformat(),
            }
            for p in projects
        ]
        job.total_rows = len(rows)

        if job.target_format == ExportFormat.JSON:
            payload = write_json_rows(rows)
            extension = "json"
        elif job.target_format == ExportFormat.YAML:
            payload = write_yaml_rows(rows)
            extension = "yaml"
        elif job.target_format == ExportFormat.PDF:
            payload = write_pdf_summary(rows, _FIELDNAMES)
            extension = "pdf"
        else:
            payload = build_export_package(
                json_bytes=write_json_rows(rows),
                yaml_bytes=write_yaml_rows(rows),
                csv_bytes=write_csv_rows(rows, _FIELDNAMES),
                row_count=len(rows),
            )
            extension = "zip"

        await self._storage.ensure_bucket(self._bucket)
        storage_key = f"exports/{job.requested_by}/{job.id}.{extension}"
        await self._storage.upload(self._bucket, storage_key, payload, "application/octet-stream")

        job.result_storage_key = storage_key
        job.status = JobStatus.COMPLETED
        job.completed_at = datetime.now(UTC)
        return job


__all__ = ["ProjectExportService"]
