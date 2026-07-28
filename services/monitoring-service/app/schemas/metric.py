"""Request/response schemas for the reusable metric definition catalog."""

from __future__ import annotations

from uuid import UUID

from pydantic import BaseModel, Field

from app.models.enums import MetricType


class MonitoringMetricCreateRequest(BaseModel):
    """Body of a request to define a reusable metric."""

    organization_id: UUID
    collector_id: UUID | None = None
    metric_type: MetricType
    name: str = Field(min_length=1, max_length=255)
    unit: str | None = Field(default=None, max_length=32)


class MonitoringMetricResponse(BaseModel):
    """A standalone, reusable definition of one thing to measure."""

    id: UUID
    organization_id: UUID
    collector_id: UUID | None
    metric_type: MetricType
    name: str
    unit: str | None


__all__ = ["MonitoringMetricCreateRequest", "MonitoringMetricResponse"]
