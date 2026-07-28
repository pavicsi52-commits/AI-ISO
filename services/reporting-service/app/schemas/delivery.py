"""Request/response schemas for scheduling, distribution, and archive."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field

from app.models.enums import (
    ArchiveStatus,
    DistributionChannel,
    DistributionStatus,
    ExportFormat,
    ScheduleFrequency,
)


class ScheduleCreateRequest(BaseModel):
    """Body of ``POST /reports/schedule``."""

    organization_id: UUID
    project_id: UUID | None = None
    report_id: UUID
    frequency: ScheduleFrequency
    starts_at: datetime
    ends_at: datetime | None = None
    cron_expression: str | None = Field(default=None, max_length=128)
    timezone: str = Field(default="UTC", max_length=64)
    """IANA zone name. "Every Monday 09:00" is a different instant in
    Berlin than in Chicago, so the zone is stored per schedule.
    """

    export_format: ExportFormat = ExportFormat.PDF
    max_retries: int = Field(default=3, ge=1, le=20)
    notify_on_failure: bool = True


class ScheduleUpdateRequest(BaseModel):
    """Body of ``PUT /reports/schedules/{id}``."""

    frequency: ScheduleFrequency | None = None
    cron_expression: str | None = Field(default=None, max_length=128)
    timezone: str | None = Field(default=None, max_length=64)
    export_format: ExportFormat | None = None
    ends_at: datetime | None = None
    enabled: bool | None = None


class ScheduleResponse(BaseModel):
    """One report schedule."""

    id: UUID
    job_id: UUID
    frequency: ScheduleFrequency
    cron_expression: str | None
    timezone: str
    export_format: ExportFormat
    starts_at: datetime
    ends_at: datetime | None
    next_run_at: datetime | None
    last_run_at: datetime | None
    max_retries: int
    consecutive_failures: int
    notify_on_failure: bool
    last_error: str | None
    enabled: bool


class RecipientCreateRequest(BaseModel):
    """Body of ``POST /reports/{id}/recipients``."""

    organization_id: UUID
    project_id: UUID | None = None
    channel: DistributionChannel
    target: str = Field(min_length=1, max_length=1024)
    export_format: ExportFormat = ExportFormat.PDF
    headers: dict[str, str] = Field(default_factory=dict)


class RecipientResponse(BaseModel):
    """One standing recipient."""

    id: UUID
    job_id: UUID
    channel: DistributionChannel
    target: str
    export_format: ExportFormat
    headers: dict[str, str]
    enabled: bool


class DistributionResponse(BaseModel):
    """One delivery attempt.

    ``share_token`` is deliberately **not** exposed here. The token is
    a bearer credential for an unauthenticated recipient; returning it
    in a list any authorised reader can fetch would widen who can open
    the link far beyond the intended recipient. It is returned once, to
    the caller who created the delivery.
    """

    id: UUID
    export_id: UUID
    recipient_id: UUID | None
    channel: DistributionChannel
    target: str
    status: DistributionStatus
    attempts: int
    expires_at: datetime | None
    storage_uri: str | None
    error_message: str | None
    delivered_at: datetime | None


class DistributeRequest(BaseModel):
    """Body of ``POST /reports/exports/{id}/distribute``."""

    channel: DistributionChannel
    target: str = Field(default="", max_length=1024)
    headers: dict[str, str] = Field(default_factory=dict)


class ShareLinkResponse(BaseModel):
    """A freshly minted shared link.

    The token is returned exactly once, here, to the caller who created
    it -- never from a listing endpoint.
    """

    distribution_id: UUID
    share_token: str
    expires_at: datetime | None


class ArchiveResponse(BaseModel):
    """One archived artifact."""

    id: UUID
    execution_id: UUID | None
    job_id: UUID | None
    title: str
    export_format: ExportFormat
    filename: str
    content_type: str
    size_bytes: int
    checksum_sha256: str
    archive_version: int
    status: ArchiveStatus
    archived_at: datetime
    retention_until: datetime | None
    purge_reason: str | None


class ArchiveRequest(BaseModel):
    """Body of ``POST /reports/archive``."""

    export_id: UUID
    title: str = Field(min_length=1, max_length=512)
    retention_days: int | None = Field(default=None, ge=1, le=36_500)


__all__ = [
    "ArchiveRequest",
    "ArchiveResponse",
    "DistributeRequest",
    "DistributionResponse",
    "RecipientCreateRequest",
    "RecipientResponse",
    "ScheduleCreateRequest",
    "ScheduleResponse",
    "ScheduleUpdateRequest",
    "ShareLinkResponse",
]
