"""Request/response schemas for ``/monitoring/slo``."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel

from app.models.enums import ComplianceStatus, SLOType


class MonitoringSLOCreateRequest(BaseModel):
    """Body of a request to register a Service Level Objective target."""

    organization_id: UUID
    target_id: UUID
    slo_type: SLOType
    objective_value: float
    period_start: datetime
    period_end: datetime


class MonitoringSLOResponse(BaseModel):
    """One Service Level Objective's own tracked target over a period."""

    id: UUID
    organization_id: UUID
    target_id: UUID
    slo_type: SLOType
    objective_value: float
    actual_value: float | None
    error_budget_remaining_percentage: float | None
    status: ComplianceStatus
    period_start: datetime
    period_end: datetime


__all__ = ["MonitoringSLOCreateRequest", "MonitoringSLOResponse"]
