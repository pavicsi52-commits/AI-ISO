"""``asset_lifecycle`` table -- lifecycle transition history. Distinct
from :attr:`~app.models.asset.Asset.lifecycle_state`, which always
holds the current value. Per docs/036 "LIFECYCLE".
"""

from __future__ import annotations

import uuid
from datetime import datetime

from shared_core.database.base import BaseModel
from sqlalchemy import DateTime, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column

from app.models.enums import LifecycleState


class AssetLifecycleHistoryEntry(BaseModel):
    """One lifecycle-state transition for an asset."""

    __tablename__ = "asset_lifecycle"

    asset_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("inventory_assets.id", ondelete="CASCADE"), nullable=False, index=True
    )
    previous_state: Mapped[LifecycleState | None] = mapped_column(String(16), default=None)
    new_state: Mapped[LifecycleState] = mapped_column(String(16))
    transitioned_by: Mapped[uuid.UUID | None] = mapped_column(default=None)
    notes: Mapped[str | None] = mapped_column(String(1024), default=None)
    transitioned_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


__all__ = ["AssetLifecycleHistoryEntry"]
