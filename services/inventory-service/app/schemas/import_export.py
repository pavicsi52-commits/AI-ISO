"""Request/response schemas for ``POST /inventory/import`` and
``POST /inventory/export``.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field
from shared_core.enums.job_status import JobStatus

from app.models.enums import AssetType, ExportFormat, ImportFormat


class ImportRequest(BaseModel):
    """Non-file fields of the multipart ``POST /inventory/import`` request."""

    organization_id: UUID
    source_format: ImportFormat
    preview_only: bool = False


class ImportJobResponse(BaseModel):
    """The status of one import job."""

    job_id: UUID
    status: JobStatus
    source_format: ImportFormat
    preview_only: bool
    total_rows: int
    processed_rows: int
    succeeded_rows: int
    failed_rows: int
    duplicate_rows: int
    error_report: list[dict[str, Any]]
    started_at: datetime | None
    completed_at: datetime | None


class ExportRequest(BaseModel):
    """Body of ``POST /inventory/export``."""

    organization_id: UUID
    target_format: ExportFormat = ExportFormat.JSON
    asset_type: AssetType | None = None
    status: str | None = None
    tags: list[str] = Field(default_factory=list)


class ExportJobResponse(BaseModel):
    """The status of one export job."""

    job_id: UUID
    status: JobStatus
    target_format: ExportFormat
    total_rows: int
    download_url: str | None
    started_at: datetime | None
    completed_at: datetime | None


__all__ = ["ExportJobResponse", "ExportRequest", "ImportJobResponse", "ImportRequest"]
