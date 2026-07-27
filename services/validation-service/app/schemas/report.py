"""Request/response schemas for ``GET /validation/reports``."""

from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel

from app.models.enums import ValidationReportType


class ValidationReportResponse(BaseModel):
    """A generated validation report."""

    id: UUID
    organization_id: UUID
    execution_id: UUID | None
    report_type: ValidationReportType
    generated_by: UUID | None
    parameters: dict[str, Any]
    result: dict[str, Any]
    generated_at: datetime


__all__ = ["ValidationReportResponse"]
