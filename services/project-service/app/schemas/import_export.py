"""Request/response schemas for ``POST /projects/import`` and ``POST /projects/export``."""

from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field
from shared_core.enums.job_status import JobStatus

from app.models.enums import ExportFormat, ImportFormat


class ImportRequest(BaseModel):
    """Non-file fields of the multipart ``POST /projects/import`` request."""

    organization_id: UUID
    source_format: ImportFormat
    preview_only: bool = False


class ImportJobResponse(BaseModel):
    """The status of one import job -- mirrors
    ``services/user-management-service``'s identical ``ImportJobResponse``
    shape plus this service's own progress-counter columns.
    """

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
    """Body of ``POST /projects/export``."""

    organization_id: UUID
    target_format: ExportFormat = ExportFormat.JSON
    status: str | None = None
    category: str | None = None
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
