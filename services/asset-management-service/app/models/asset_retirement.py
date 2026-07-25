"""``asset_retirement`` table. Per docs/038 "ASSET STATUS" (Retired,
Disposed) and "LIFECYCLE MANAGEMENT" "Support" (Retire, Dispose).
"""

from __future__ import annotations

import uuid
from datetime import datetime

from shared_core.database.base import BaseModel
from sqlalchemy import DateTime, ForeignKey, Numeric, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column


class AssetRetirement(BaseModel):
    """One managed asset's retirement and disposal record."""

    __tablename__ = "asset_retirement"
    __table_args__ = (
        UniqueConstraint("managed_asset_id", name="uq_asset_retirement_managed_asset"),
    )

    managed_asset_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("managed_assets.id", ondelete="CASCADE"), nullable=False, index=True
    )
    retired_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    retired_by: Mapped[uuid.UUID | None] = mapped_column(default=None)
    reason: Mapped[str | None] = mapped_column(String(1024), default=None)
    disposed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)
    disposal_method: Mapped[str | None] = mapped_column(String(255), default=None)
    residual_value_realized: Mapped[float | None] = mapped_column(Numeric(14, 2), default=None)


__all__ = ["AssetRetirement"]
