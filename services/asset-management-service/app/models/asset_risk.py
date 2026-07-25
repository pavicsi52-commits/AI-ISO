"""``asset_risk`` table. Per docs/038 "RISK MANAGEMENT" "Evaluate":
Operational, Security, Business, Vendor, Compliance Risk; Risk
Scoring; Mitigation Plans; Risk History (each evaluation inserts a new
row, so the table also serves as its own risk history).
"""

from __future__ import annotations

import uuid
from datetime import datetime

from shared_core.database.base import BaseModel
from sqlalchemy import DateTime, ForeignKey, Numeric, String
from sqlalchemy.orm import Mapped, mapped_column

from app.models.enums import RiskLevel, RiskType


class AssetRisk(BaseModel):
    """One risk-type evaluation recorded against a managed asset."""

    __tablename__ = "asset_risk"

    managed_asset_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("managed_assets.id", ondelete="CASCADE"), nullable=False, index=True
    )
    risk_type: Mapped[RiskType] = mapped_column(String(16), index=True)
    level: Mapped[RiskLevel] = mapped_column(String(16), default=RiskLevel.LOW, index=True)
    score: Mapped[float] = mapped_column(Numeric(5, 2), default=0)
    mitigation_plan: Mapped[str | None] = mapped_column(String(2048), default=None)
    evaluated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)


__all__ = ["AssetRisk"]
