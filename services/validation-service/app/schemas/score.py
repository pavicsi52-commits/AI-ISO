"""Response schema for the weighted scoring rollup of one execution."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel


class ValidationScoreResponse(BaseModel):
    """The weighted scoring rollup for one execution."""

    id: UUID
    execution_id: UUID
    overall_score: float
    infrastructure_score: float | None
    security_score: float | None
    compliance_score: float | None
    configuration_score: float | None
    performance_score: float | None
    health_score: float | None
    computed_at: datetime | None


__all__ = ["ValidationScoreResponse"]
