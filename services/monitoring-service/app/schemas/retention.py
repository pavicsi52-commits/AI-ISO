"""Request/response schemas for retention/downsampling policies."""

from __future__ import annotations

from uuid import UUID

from pydantic import BaseModel, Field

from app.models.enums import AggregationFunction, MetricType


class MonitoringRetentionCreateRequest(BaseModel):
    """Body of a request to set a retention/downsampling policy."""

    organization_id: UUID
    metric_type: MetricType | None = None
    retention_days: int = Field(default=90, gt=0)
    downsampling_function: AggregationFunction | None = None
    downsampling_interval_seconds: float | None = Field(default=None, gt=0)
    is_active: bool = True


class MonitoringRetentionResponse(BaseModel):
    """A retention/downsampling policy, optionally scoped to one metric type."""

    id: UUID
    organization_id: UUID
    metric_type: MetricType | None
    retention_days: int
    downsampling_function: AggregationFunction | None
    downsampling_interval_seconds: float | None
    is_active: bool


__all__ = ["MonitoringRetentionCreateRequest", "MonitoringRetentionResponse"]
