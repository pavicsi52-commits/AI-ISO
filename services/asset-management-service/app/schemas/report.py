"""Request/response schemas for ``GET /assets/reports``."""

from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field

from app.models.enums import ReportType


class AssetReportGenerateRequest(BaseModel):
    """Query parameters accepted by ``GET /assets/reports``."""

    report_type: ReportType
    managed_asset_id: UUID | None = None
    parameters: dict[str, Any] = Field(default_factory=dict)


class AssetReportResponse(BaseModel):
    """One generated asset-management report."""

    id: UUID
    organization_id: UUID
    managed_asset_id: UUID | None
    report_type: ReportType
    generated_by: UUID | None
    parameters: dict[str, Any]
    result: dict[str, Any]
    generated_at: datetime


__all__ = ["AssetReportGenerateRequest", "AssetReportResponse"]
