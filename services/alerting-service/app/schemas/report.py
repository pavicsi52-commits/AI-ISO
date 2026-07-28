"""Request/response schemas for ``GET /alert-reports``."""

from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field

from app.models.enums import AlertReportType


class AlertReportGenerateRequest(BaseModel):
    """Body of a request to generate an alerting report."""

    organization_id: UUID
    alert_id: UUID | None = None
    report_type: AlertReportType
    parameters: dict[str, Any] = Field(default_factory=dict)


class AlertReportResponse(BaseModel):
    """A generated alerting report."""

    id: UUID
    organization_id: UUID
    alert_id: UUID | None
    report_type: AlertReportType
    generated_by: UUID | None
    parameters: dict[str, Any]
    result: dict[str, Any]
    generated_at: datetime


__all__ = ["AlertReportGenerateRequest", "AlertReportResponse"]
