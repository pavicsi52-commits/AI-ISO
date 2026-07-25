"""Response schema for ``GET /automation/reports``."""

from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel

from app.models.enums import AutomationReportType


class AutomationReportResponse(BaseModel):
    """One generated automation report."""

    id: UUID
    organization_id: UUID
    job_id: UUID | None
    report_type: AutomationReportType
    generated_by: UUID | None
    parameters: dict[str, Any]
    result: dict[str, Any]
    generated_at: datetime


__all__ = ["AutomationReportResponse"]
