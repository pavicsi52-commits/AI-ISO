"""Response schema for :class:`~app.models.workflow_report.WorkflowReport`,
backing ``GET /workflow/reports``.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel

from app.models.enums import WorkflowReportType


class WorkflowReportResponse(BaseModel):
    """One generated workflow-runtime report."""

    id: UUID
    organization_id: UUID
    instance_id: UUID | None
    report_type: WorkflowReportType
    generated_by: UUID | None
    parameters: dict[str, Any]
    result: dict[str, Any]
    generated_at: datetime


__all__ = ["WorkflowReportResponse"]
