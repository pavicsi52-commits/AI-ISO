"""``asset_depreciation`` table. Per docs/038 "DEPRECIATION" "Support":
Straight Line, Declining Balance, Units of Production, Custom
Policies, Book Value, Residual Value, Depreciation Reports.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from shared_core.database.base import BaseModel
from sqlalchemy import DateTime, ForeignKey, Integer, Numeric, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.models.enums import DepreciationMethod


class AssetDepreciation(BaseModel):
    """One managed asset's depreciation policy and current book value."""

    __tablename__ = "asset_depreciation"
    __table_args__ = (
        UniqueConstraint("managed_asset_id", name="uq_asset_depreciation_managed_asset"),
    )

    managed_asset_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("managed_assets.id", ondelete="CASCADE"), nullable=False, index=True
    )
    method: Mapped[DepreciationMethod] = mapped_column(
        String(24), default=DepreciationMethod.STRAIGHT_LINE
    )
    acquisition_cost: Mapped[float] = mapped_column(Numeric(14, 2), default=0)
    residual_value: Mapped[float] = mapped_column(Numeric(14, 2), default=0)
    useful_life_months: Mapped[int] = mapped_column(Integer, default=0)
    book_value: Mapped[float] = mapped_column(Numeric(14, 2), default=0)
    last_computed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)


__all__ = ["AssetDepreciation"]
