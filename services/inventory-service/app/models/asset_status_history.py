"""``asset_status`` table -- status *transition history*. Distinct from
:attr:`~app.models.asset.Asset.status`, which always holds the current
value; this table records every transition, matching the
"current value on the entity + separate history table" split every
prior AI-IOS versioned-state concern in this codebase already uses.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from shared_core.database.base import BaseModel
from sqlalchemy import DateTime, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column

from app.models.enums import AssetStatus


class AssetStatusHistoryEntry(BaseModel):
    """One status transition for an asset."""

    __tablename__ = "asset_status"

    asset_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("inventory_assets.id", ondelete="CASCADE"), nullable=False, index=True
    )
    previous_status: Mapped[AssetStatus | None] = mapped_column(String(16), default=None)
    new_status: Mapped[AssetStatus] = mapped_column(String(16))
    changed_by: Mapped[uuid.UUID | None] = mapped_column(default=None)
    reason: Mapped[str | None] = mapped_column(String(1024), default=None)
    changed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


__all__ = ["AssetStatusHistoryEntry"]
