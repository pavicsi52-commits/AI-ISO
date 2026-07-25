"""``asset_costs`` table. Per docs/038 "COST MANAGEMENT" "Track": 9
cost types plus "Total Cost of Ownership (TCO)" -- TCO is computed by
summing this table's rows for an asset rather than persisted as its
own cost type (see :class:`~app.models.enums.CostType`).
"""

from __future__ import annotations

import uuid
from datetime import datetime

from shared_core.database.base import BaseModel
from sqlalchemy import DateTime, ForeignKey, Numeric, String
from sqlalchemy.orm import Mapped, mapped_column

from app.models.enums import CostType


class AssetCost(BaseModel):
    """One cost entry incurred against a managed asset."""

    __tablename__ = "asset_costs"

    managed_asset_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("managed_assets.id", ondelete="CASCADE"), nullable=False, index=True
    )
    cost_type: Mapped[CostType] = mapped_column(String(16), index=True)
    amount: Mapped[float] = mapped_column(Numeric(14, 2))
    currency: Mapped[str] = mapped_column(String(8), default="USD")
    incurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    description: Mapped[str | None] = mapped_column(String(1024), default=None)


__all__ = ["AssetCost"]
