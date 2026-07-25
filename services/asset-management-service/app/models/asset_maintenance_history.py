"""``asset_maintenance_history`` table -- a narrative timeline of
maintenance events, distinct from :mod:`app.models.asset_maintenance`'s
scheduled/tracked activities: covers window executions, ad-hoc field
notes, and any other maintenance-adjacent event worth recording even
when no formal :class:`~app.models.asset_maintenance.AssetMaintenance`
row exists for it.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from shared_core.database.base import BaseModel
from sqlalchemy import JSON, DateTime, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column


class AssetMaintenanceHistoryEntry(BaseModel):
    """One maintenance timeline entry for a managed asset."""

    __tablename__ = "asset_maintenance_history"

    managed_asset_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("managed_assets.id", ondelete="CASCADE"), nullable=False, index=True
    )
    maintenance_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("asset_maintenance.id", ondelete="SET NULL"), default=None
    )
    event_type: Mapped[str] = mapped_column(String(64))
    detail: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)


__all__ = ["AssetMaintenanceHistoryEntry"]
