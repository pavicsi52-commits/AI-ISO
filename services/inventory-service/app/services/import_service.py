"""Bulk asset import.

Per docs/036 "IMPORT": CSV, Excel, JSON, YAML, ZIP, Bulk Import,
Validation, Preview, Rollback. Per "PERFORMANCE": "Background
Processing" -- :meth:`AssetImportService.create_job` only uploads the
file and enqueues a job (fast, request-scoped);
:meth:`AssetImportService.process_job` does the actual parsing/
validation/row-creation and is what a queue consumer
(:mod:`app.workers.import_worker`) calls. Mirrors
``services/project-service``'s identical ``ProjectImportService`` shape.
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

from app.models.asset_import_job import AssetImportJob
from app.models.enums import AssetType, Criticality, ImportFormat
from app.parsers.csv_parser import parse_csv_rows
from app.parsers.excel_parser import parse_excel_rows
from app.parsers.json_parser import parse_json_rows
from app.parsers.yaml_parser import parse_yaml_rows
from app.parsers.zip_archive import extract_single_data_file
from app.repositories.asset_import_job import AssetImportJobRepository
from app.services.asset import AssetService

_REQUIRED_FIELDS = ("name", "asset_type")


def _parse_rows(  # noqa: PLR0911 -- one dispatch branch per supported format, inherently branchy
    source_format: ImportFormat, content: bytes
) -> list[dict[str, Any]]:
    if source_format == ImportFormat.JSON:
        return parse_json_rows(content)
    if source_format == ImportFormat.YAML:
        return parse_yaml_rows(content)
    if source_format == ImportFormat.CSV:
        return list(parse_csv_rows(content))
    if source_format == ImportFormat.EXCEL:
        return list(parse_excel_rows(content))
    filename, extracted = extract_single_data_file(content)
    if filename.lower().endswith((".yaml", ".yml")):
        return parse_yaml_rows(extracted)
    if filename.lower().endswith(".csv"):
        return list(parse_csv_rows(extracted))
    if filename.lower().endswith(".xlsx"):
        return list(parse_excel_rows(extracted))
    return parse_json_rows(extracted)


class AssetImportService:
    """Uploads, processes, previews, and rolls back bulk asset-import jobs."""

    def __init__(
        self,
        jobs: AssetImportJobRepository,
        assets: AssetService,
        storage: StorageWrapper,
        session: AsyncSession,
        *,
        bucket: str,
    ) -> None:
        self._jobs = jobs
        self._assets = assets
        self._storage = storage
        self._session = session
        self._bucket = bucket

    async def create_job(
        self,
        requested_by: UUID,
        *,
        organization_id: UUID,
        source_format: ImportFormat,
        filename: str,
        content: bytes,
        preview_only: bool,
    ) -> AssetImportJob:
        """Upload *content* and queue a bulk import job ("Bulk Import").

        Commits immediately after creating the job row -- the request
        handler publishes a queue message right after this returns, and
        the in-process worker consuming it uses a *different* database
        session/connection. A same-process RabbitMQ round trip can be
        fast enough that the worker's own read arrives before this
        request's own ``session_scope`` dependency teardown would
        otherwise have committed, producing a real, deterministic
        ``NotFoundError`` -- the exact bug class
        ``services/project-service``'s own ``ProjectImportService
        .create_job`` was caught making live, fixed the same way here
        proactively.
        """
        await self._storage.ensure_bucket(self._bucket)
        storage_key = f"imports/{requested_by}/{datetime.now(UTC).timestamp()}_{filename}"
        await self._storage.upload(self._bucket, storage_key, content, "application/octet-stream")
        job = await self._jobs.create(
            AssetImportJob(
                requested_by=requested_by,
                organization_id=organization_id,
                source_format=source_format,
                source_storage_key=storage_key,
                preview_only=preview_only,
                status=JobStatus.QUEUED,
            )
        )
        await self._session.commit()
        return job

    async def get_job(self, job_id: UUID) -> AssetImportJob:
        """Return one import job by id.

        Raises:
            NotFoundError: If no such job exists.
        """
        return await self._jobs.require_by_id(job_id)

    async def process_job(self, job_id: UUID) -> AssetImportJob:
        """Download, parse, validate, and (unless previewing) create assets
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

        seen_identifiers: set[str] = set()
        errors: list[dict[str, Any]] = []
        created_ids: list[str] = []

        for index, row in enumerate(rows):
            job.processed_rows += 1
            missing = [field for field in _REQUIRED_FIELDS if not row.get(field)]
            if missing:
                job.failed_rows += 1
                errors.append({"row": index, "error": f"Missing required fields: {missing}"})
                continue
            identifier = str(
                row.get("hostname") or row.get("serial_number") or row.get("mac_address") or ""
            )
            if identifier and identifier in seen_identifiers:
                job.duplicate_rows += 1
                errors.append({"row": index, "error": "Duplicate identifier within import file"})
                continue
            if identifier:
                seen_identifiers.add(identifier)

            if job.preview_only:
                job.succeeded_rows += 1
                continue
            try:
                asset = await self._assets.create(
                    organization_id=job.organization_id,
                    project_id=None,
                    name=str(row["name"]),
                    display_name=row.get("display_name") or None,
                    hostname=row.get("hostname") or None,
                    fqdn=row.get("fqdn") or None,
                    ip_address=row.get("ip_address") or None,
                    mac_address=row.get("mac_address") or None,
                    serial_number=row.get("serial_number") or None,
                    vendor=row.get("vendor") or None,
                    manufacturer=row.get("manufacturer") or None,
                    model=row.get("model") or None,
                    firmware_version=row.get("firmware_version") or None,
                    operating_system=row.get("operating_system") or None,
                    architecture=row.get("architecture") or None,
                    environment=row.get("environment") or None,
                    asset_type=AssetType(str(row["asset_type"])),
                    category_id=None,
                    class_id=None,
                    location_id=None,
                    owner_id=job.requested_by,
                    criticality=Criticality(row.get("criticality") or "medium"),
                    metadata=row.get("metadata") or {},
                    tags=[],
                    created_by=job.requested_by,
                )
                created_ids.append(str(asset.id))
                job.succeeded_rows += 1
            except (ConflictError, ValueError) as exc:
                job.failed_rows += 1
                errors.append({"row": index, "error": str(exc)})

        job.error_report = errors
        job.created_asset_ids = created_ids
        job.status = JobStatus.COMPLETED
        job.completed_at = datetime.now(UTC)
        return job

    async def rollback_job(self, job_id: UUID) -> AssetImportJob:
        """Soft-delete every asset *job_id* created ("Rollback").

        Raises:
            ConflictError: If *job_id* was never completed, or was preview-only.
        """
        job = await self._jobs.require_by_id(job_id)
        if job.status != JobStatus.COMPLETED or job.preview_only:
            raise ConflictError(f"Import job '{job_id}' has nothing to roll back.")
        for raw_asset_id in job.created_asset_ids:
            await self._assets.delete(UUID(raw_asset_id), actor_id=job.requested_by)
        job.rolled_back_at = datetime.now(UTC)
        return job


__all__ = ["AssetImportService"]
