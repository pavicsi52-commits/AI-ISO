"""Response schema for ``/projects/{id}/analytics``."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel


class ProjectStatisticsResponse(BaseModel):
    """One project's usage analytics snapshot."""

    project_id: UUID
    member_count: int
    automation_count: int
    workflow_count: int
    validation_count: int
    inventory_count: int
    connector_count: int
    ai_usage_count: int
    storage_usage_bytes: int
    execution_count: int
    failure_count: int
    success_count: int
    success_rate_percent: float
    computed_at: datetime


__all__ = ["ProjectStatisticsResponse"]
