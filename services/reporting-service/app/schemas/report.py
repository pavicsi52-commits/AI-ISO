"""Request/response schemas for reports, executions, and exports."""

from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field

from app.models.enums import (
    ExportFormat,
    ReportCategory,
    ReportExecutionStatus,
    ReportType,
)


class ReportCreateRequest(BaseModel):
    """Body of ``POST /reports``."""

    organization_id: UUID
    project_id: UUID | None = None
    name: str = Field(min_length=1, max_length=255)
    description: str | None = None
    category: ReportCategory
    report_type: ReportType
    template_id: UUID | None = None
    default_format: ExportFormat = ExportFormat.PDF
    parameter_values: dict[str, Any] = Field(default_factory=dict)
    filters: list[dict[str, Any]] = Field(default_factory=list)


class ReportUpdateRequest(BaseModel):
    """Body of ``PUT /reports/{id}``.

    Every field is optional: this is a partial update, so omitting a
    field leaves it alone rather than clearing it.
    """

    name: str | None = Field(default=None, min_length=1, max_length=255)
    description: str | None = None
    default_format: ExportFormat | None = None
    parameter_values: dict[str, Any] | None = None
    filters: list[dict[str, Any]] | None = None
    enabled: bool | None = None


class ReportResponse(BaseModel):
    """One saved report."""

    id: UUID
    organization_id: UUID
    project_id: UUID | None
    template_id: UUID | None
    name: str
    description: str | None
    category: ReportCategory
    report_type: ReportType
    default_format: ExportFormat
    parameter_values: dict[str, Any]
    filters: list[dict[str, Any]]
    enabled: bool
    owner_id: UUID | None


class ReportGenerateRequest(BaseModel):
    """Body of ``POST /reports/generate``."""

    report_id: UUID
    export_formats: list[ExportFormat] = Field(default_factory=list)
    parameter_values: dict[str, Any] = Field(default_factory=dict)
    filters: list[dict[str, Any]] | None = None
    distribute: bool = False
    """Whether to deliver to the report's standing recipients."""

    archive: bool = False
    signed_by: str | None = Field(default=None, max_length=255)
    pdf_password: str | None = Field(default=None, min_length=4, max_length=128)


class ExportSummary(BaseModel):
    """One rendered artifact, without its bytes.

    The content is deliberately absent: a JSON response carrying a
    multi-megabyte base64 PDF would be unusable. Artifacts are fetched
    through their own download endpoint.
    """

    id: UUID
    execution_id: UUID
    export_format: ExportFormat
    filename: str
    content_type: str
    size_bytes: int
    checksum_sha256: str
    download_count: int


class ExecutionResponse(BaseModel):
    """One generation run."""

    id: UUID
    job_id: UUID
    schedule_id: UUID | None
    status: ReportExecutionStatus
    row_count: int
    section_count: int
    duration_ms: float | None
    error_message: str | None
    triggered_by: UUID | None
    started_at: datetime | None
    finished_at: datetime | None


class GenerateResponse(BaseModel):
    """What one generation run produced."""

    execution: ExecutionResponse
    exports: list[ExportSummary]
    degraded_sections: list[str] = Field(default_factory=list)
    """Sections that could not be resolved.

    Surfaced explicitly so a caller can tell a complete report from one
    delivered with a visible gap.
    """

    distributions: list[UUID] = Field(default_factory=list)
    archive_id: UUID | None = None


class ExportRequest(BaseModel):
    """Body of ``POST /reports/export`` -- re-export an existing run."""

    execution_id: UUID
    export_format: ExportFormat
    signed_by: str | None = Field(default=None, max_length=255)
    pdf_password: str | None = Field(default=None, min_length=4, max_length=128)


class HistoryResponse(BaseModel):
    """One user-visible history entry."""

    id: UUID
    job_id: UUID
    execution_id: UUID | None
    event: str
    summary: str
    details: dict[str, Any]
    actor_id: UUID | None
    occurred_at: datetime


class StatisticsResponse(BaseModel):
    """An organization's reporting analytics."""

    total_reports: int
    total_executions: int
    successful_executions: int
    failed_executions: int
    scheduled_executions: int
    total_downloads: int
    total_distributions: int
    failed_distributions: int
    average_duration_ms: float
    popular_reports: dict[str, Any]
    export_format_usage: dict[str, Any]
    template_usage: dict[str, Any]
    schedule_usage: dict[str, Any]
    distribution_usage: dict[str, Any]
    computed_at: datetime


__all__ = [
    "ExecutionResponse",
    "ExportRequest",
    "ExportSummary",
    "GenerateResponse",
    "HistoryResponse",
    "ReportCreateRequest",
    "ReportGenerateRequest",
    "ReportResponse",
    "ReportUpdateRequest",
    "StatisticsResponse",
]
