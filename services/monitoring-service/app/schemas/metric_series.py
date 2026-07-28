"""Request/response schemas for time-series metric data points."""

from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field


class MonitoringMetricSeriesIngestRequest(BaseModel):
    """Body of a request to record one measured data point."""

    metric_id: UUID
    target_id: UUID
    value: float
    tags: dict[str, Any] = Field(default_factory=dict)
    recorded_at: datetime | None = None


class MonitoringMetricSeriesResponse(BaseModel):
    """One measured data point for a metric against a target."""

    id: UUID
    organization_id: UUID
    metric_id: UUID
    target_id: UUID
    value: float
    tags: dict[str, Any]
    recorded_at: datetime


__all__ = ["MonitoringMetricSeriesIngestRequest", "MonitoringMetricSeriesResponse"]
