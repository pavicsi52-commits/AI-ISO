"""Request/response schemas for ``GET/POST /configurations/reports``."""

from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field

from app.models.enums import ConfigReportType


class ConfigurationReportGenerateRequest(BaseModel):
    """Body of ``POST /configurations/reports``."""

    organization_id: UUID
    profile_id: UUID | None = None
    report_type: ConfigReportType
    generated_by: UUID | None = None
    parameters: dict[str, Any] = Field(default_factory=dict)


class ConfigurationReportResponse(BaseModel):
    """One generated configuration-management report."""

    id: UUID
    organization_id: UUID
    profile_id: UUID | None
    report_type: ConfigReportType
    generated_by: UUID | None
    parameters: dict[str, Any]
    result: dict[str, Any]
    generated_at: datetime


__all__ = ["ConfigurationReportGenerateRequest", "ConfigurationReportResponse"]
