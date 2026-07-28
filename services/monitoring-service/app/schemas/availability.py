"""Response schema for ``GET /monitoring/availability``."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel

from app.models.enums import AvailabilityStatus


class MonitoringAvailabilityResponse(BaseModel):
    """One uptime/downtime/maintenance interval for a target."""

    id: UUID
    organization_id: UUID
    target_id: UUID
    status: AvailabilityStatus
    started_at: datetime
    ended_at: datetime | None
    duration_seconds: float | None


__all__ = ["MonitoringAvailabilityResponse"]
