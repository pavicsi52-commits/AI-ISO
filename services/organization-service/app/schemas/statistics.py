"""Response schema for ``GET /organizations/{id}/analytics``."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel


class OrganizationStatisticsResponse(BaseModel):
    """One organization's last-computed usage snapshot ("ORGANIZATION ANALYTICS")."""

    organization_id: UUID
    user_count: int
    project_count: int
    asset_count: int
    workflow_count: int
    automation_count: int
    validation_count: int
    storage_usage_bytes: int
    api_usage_count: int
    ai_usage_count: int
    license_utilization_percent: float
    computed_at: datetime


__all__ = ["OrganizationStatisticsResponse"]
