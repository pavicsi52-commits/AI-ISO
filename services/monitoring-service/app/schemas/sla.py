"""Request/response schemas for ``/monitoring/sla``."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field

from app.models.enums import ComplianceStatus, SLAType


class MonitoringSLACreateRequest(BaseModel):
    """Body of a request to register a Service Level Agreement objective."""

    organization_id: UUID
    target_id: UUID
    sla_type: SLAType
    objective_percentage: float = Field(gt=0, le=100)
    period_start: datetime
    period_end: datetime


class MonitoringSLAResponse(BaseModel):
    """One Service Level Agreement's own tracked objective over a period."""

    id: UUID
    organization_id: UUID
    target_id: UUID
    sla_type: SLAType
    objective_percentage: float
    actual_percentage: float | None
    status: ComplianceStatus
    period_start: datetime
    period_end: datetime


__all__ = ["MonitoringSLACreateRequest", "MonitoringSLAResponse"]
