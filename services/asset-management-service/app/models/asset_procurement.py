"""``asset_procurement`` table. Per docs/038 "PROCUREMENT" "Track":
Purchase Order, Invoice, Cost Center, Supplier, Acquisition Cost,
Purchase Date, Expected Lifetime, Financial Metadata.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from shared_core.database.base import BaseModel
from sqlalchemy import JSON, DateTime, ForeignKey, Integer, Numeric, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column


class AssetProcurement(BaseModel):
    """One managed asset's procurement record."""

    __tablename__ = "asset_procurement"
    __table_args__ = (
        UniqueConstraint("managed_asset_id", name="uq_asset_procurement_managed_asset"),
    )

    managed_asset_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("managed_assets.id", ondelete="CASCADE"), nullable=False, index=True
    )
    vendor_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("asset_vendors.id", ondelete="SET NULL"), default=None
    )
    purchase_order_number: Mapped[str | None] = mapped_column(String(128), default=None)
    invoice_number: Mapped[str | None] = mapped_column(String(128), default=None)
    cost_center: Mapped[str | None] = mapped_column(String(128), default=None)
    acquisition_cost: Mapped[float] = mapped_column(Numeric(14, 2), default=0)
    purchase_date: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)
    expected_lifetime_months: Mapped[int | None] = mapped_column(Integer, default=None)
    financial_metadata: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)


__all__ = ["AssetProcurement"]
