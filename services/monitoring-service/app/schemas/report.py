"""Request/response schemas for ``GET /monitoring/reports``."""

from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field

from app.models.enums import MonitoringReportType


class MonitoringReportGenerateRequest(BaseModel):
    """Body of a request to generate a monitoring report."""

    organization_id: UUID
    target_id: UUID | None = None
    report_type: MonitoringReportType
    parameters: dict[str, Any] = Field(default_factory=dict)


class MonitoringReportResponse(BaseModel):
    """A generated monitoring report."""

    id: UUID
    organization_id: UUID
    target_id: UUID | None
    report_type: MonitoringReportType
    generated_by: UUID | None
    parameters: dict[str, Any]
    result: dict[str, Any]
    generated_at: datetime


__all__ = ["MonitoringReportGenerateRequest", "MonitoringReportResponse"]
