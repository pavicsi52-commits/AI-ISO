"""Response schema for ``GET /assets/{id}/risk``."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel

from app.models.enums import RiskLevel, RiskType


class AssetRiskResponse(BaseModel):
    """One risk-type evaluation."""

    id: UUID
    managed_asset_id: UUID
    risk_type: RiskType
    level: RiskLevel
    score: float
    mitigation_plan: str | None
    evaluated_at: datetime


__all__ = ["AssetRiskResponse"]
