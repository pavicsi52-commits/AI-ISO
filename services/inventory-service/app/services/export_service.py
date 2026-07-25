"""Bulk asset export.

Per docs/036 "EXPORT": CSV, Excel, JSON, YAML, PDF, ZIP, Background
Processing, Audit. Mirrors ``services/project-service``'s identical
``ProjectExportService`` shape.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from shared_core.enums.job_status import JobStatus
from shared_core.exceptions.conflict import ConflictError
from shared_core.storage import StorageWrapper
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.asset_export_job import AssetExportJob
from app.models.enums import ExportFormat
from app.parsers.csv_parser import write_csv_rows
from app.parsers.excel_parser import write_excel_rows
from app.parsers.json_parser import write_json_rows
from app.parsers.pdf_writer import write_pdf_summary
from app.parsers.yaml_parser import write_yaml_rows
from app.parsers.zip_archive import build_export_package
from app.repositories.asset import AssetRepository
from app.repositories.asset_export_job import AssetExportJobRepository
from app.repositories.asset_tag import AssetTagRepository

_FIELDNAMES = [
    "id",
    "organization_id",
    "name",
    "hostname",
    "asset_type",
    "status",
    "health",
    "lifecycle_state",
    "criticality",
    "owner_id",
    "vendor",
    "model",
    "operating_system",
    "created_at",
]


class AssetExportService:
    """Requests, processes, and reports on bulk asset-export jobs."""

    def __init__(
        self,
        jobs: AssetExportJobRepository,
        assets: AssetRepository,
        tags: AssetTagRepository,
        storage: StorageWrapper,
        session: AsyncSession,
        *,
        bucket: str,
    ) -> None:
        self._jobs = jobs
        self._assets = assets
        self._tags = tags
        self._storage = storage
        self._session = session
        self._bucket = bucket

    async def create_job(
        self,
        requested_by: UUID,
        *,
        organization_id: UUID,
        target_format: ExportFormat,
        filter_criteria: dict[str, Any],
    ) -> AssetExportJob:
        """Queue a bulk export job ("Background Processing").

        Commits immediately -- see
        ``app/services/import_service.py::AssetImportService.create_job``'s
        docstring for why a job about to be handed to an independent
        queue-consumer worker can't wait for the ordinary end-of-request
        commit.
        """
        job = await self._jobs.create(
            AssetExportJob(
                requested_by=requested_by,
                organization_id=organization_id,
                target_format=target_format,
                filter_criteria=filter_criteria,
                status=JobStatus.QUEUED,
            )
        )
        await self._session.commit()
        return job

    async def get_job(self, job_id: UUID) -> AssetExportJob:
        """Return one export job by id.

        Raises:
            NotFoundError: If no such job exists.
        """
        return await self._jobs.require_by_id(job_id)

    async def download_url(self, job: AssetExportJob, *, expires_seconds: int = 3600) -> str | None:
        """A presigned, time-limited download URL for a completed job's
        result, or ``None`` if the job hasn't produced one yet.
        """
        if job.result_storage_key is None:
            return None
        return await self._storage.presigned_url(
            self._bucket, job.result_storage_key, expires_seconds
        )

    async def process_job(self, job_id: UUID) -> AssetExportJob:
        """Query, serialize, and upload the result for *job_id*.

        Raises:
            ConflictError: If *job_id* isn't in a processable state.
        """
        job = await self._jobs.require_by_id(job_id)
        if job.status not in (JobStatus.QUEUED, JobStatus.PENDING):
            raise ConflictError(f"Export job '{job_id}' is not queued for processing.")

        job.status = JobStatus.RUNNING
        job.started_at = datetime.now(UTC)

        asset_type = job.filter_criteria.get("asset_type")
        status = job.filter_criteria.get("status")
        tag_labels: list[str] = job.filter_criteria.get("tags") or []

        assets = await self._assets.list_for_org(job.organization_id)
        if asset_type:
            assets = [a for a in assets if str(a.asset_type) == asset_type]
        if status:
            assets = [a for a in assets if str(a.status) == status]
        if tag_labels:
            tagged: list[Any] = []
            for asset in assets:
                labels = {tag.label for tag in await self._tags.list_for_asset(asset.id)}
                if labels & set(tag_labels):
                    tagged.append(asset)
            assets = tagged

        rows = [
            {
                "id": str(a.id),
                "organization_id": str(a.organization_id),
                "name": a.name,
                "hostname": a.hostname or "",
                "asset_type": str(a.asset_type),
                "status": str(a.status),
                "health": str(a.health),
                "lifecycle_state": str(a.lifecycle_state),
                "criticality": str(a.criticality),
                "owner_id": str(a.owner_id) if a.owner_id else "",
                "vendor": a.vendor or "",
                "model": a.model or "",
                "operating_system": a.operating_system or "",
                "created_at": a.created_at.isoformat(),
            }
            for a in assets
        ]
        job.total_rows = len(rows)

        if job.target_format == ExportFormat.JSON:
            payload = write_json_rows(rows)
            extension = "json"
        elif job.target_format == ExportFormat.YAML:
            payload = write_yaml_rows(rows)
            extension = "yaml"
        elif job.target_format == ExportFormat.CSV:
            payload = write_csv_rows(rows, _FIELDNAMES)
            extension = "csv"
        elif job.target_format == ExportFormat.EXCEL:
            payload = write_excel_rows(rows, _FIELDNAMES)
            extension = "xlsx"
        elif job.target_format == ExportFormat.PDF:
            payload = write_pdf_summary(rows, _FIELDNAMES)
            extension = "pdf"
        else:
            payload = build_export_package(
                json_bytes=write_json_rows(rows),
                yaml_bytes=write_yaml_rows(rows),
                csv_bytes=write_csv_rows(rows, _FIELDNAMES),
                excel_bytes=write_excel_rows(rows, _FIELDNAMES),
                pdf_bytes=write_pdf_summary(rows, _FIELDNAMES),
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


__all__ = ["AssetExportService"]
