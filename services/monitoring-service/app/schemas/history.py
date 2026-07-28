"""Response schema for lightweight per-target historical health trend rows."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel
from shared_core.enums.health_status import HealthStatus


class MonitoringHistoryResponse(BaseModel):
    """One lightweight, per-target historical health snapshot."""

    id: UUID
    organization_id: UUID
    target_id: UUID
    status: HealthStatus
    score: float | None
    recorded_at: datetime


__all__ = ["MonitoringHistoryResponse"]
