"""``asset_health`` table -- health check result history. Distinct from
:attr:`~app.models.asset.Asset.health`, which always holds the current
value. Per docs/036 "HEALTH STATUS".
"""

from __future__ import annotations

import uuid
from datetime import datetime

from shared_core.database.base import BaseModel
from sqlalchemy import DateTime, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column

from app.models.enums import HealthStatus


class AssetHealthHistoryEntry(BaseModel):
    """One health check result for an asset."""

    __tablename__ = "asset_health"

    asset_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("inventory_assets.id", ondelete="CASCADE"), nullable=False, index=True
    )
    health_status: Mapped[HealthStatus] = mapped_column(String(16))
    detail: Mapped[str | None] = mapped_column(String(2048), default=None)
    checked_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


__all__ = ["AssetHealthHistoryEntry"]
