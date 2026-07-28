"""Request/response schemas for ``/monitoring/thresholds``."""

from __future__ import annotations

from uuid import UUID

from pydantic import BaseModel

from app.models.enums import ThresholdType


class MonitoringThresholdCreateRequest(BaseModel):
    """Body of ``POST /monitoring/thresholds``."""

    organization_id: UUID
    metric_id: UUID
    threshold_type: ThresholdType = ThresholdType.STATIC
    informational: float | None = None
    low: float | None = None
    medium: float | None = None
    high: float | None = None
    critical: float | None = None
    is_active: bool = True


class MonitoringThresholdResponse(BaseModel):
    """A persisted threshold configuration for a metric."""

    id: UUID
    organization_id: UUID
    metric_id: UUID
    threshold_type: ThresholdType
    informational: float | None
    low: float | None
    medium: float | None
    high: float | None
    critical: float | None
    is_active: bool


__all__ = ["MonitoringThresholdCreateRequest", "MonitoringThresholdResponse"]
