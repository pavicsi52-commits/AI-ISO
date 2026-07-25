"""``asset_maintenance_windows`` table. Per docs/038 "MAINTENANCE
WINDOWS" "Support": Recurring Windows, One-Time Windows, Downtime
Tracking, Approval, Notifications, Execution History (execution
history itself is recorded in
:mod:`app.models.asset_maintenance_history`, one row per actual
execution of a window).
"""

from __future__ import annotations

import uuid
from datetime import datetime

from shared_core.database.base import BaseModel
from sqlalchemy import Boolean, DateTime, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column

from app.models.enums import MaintenanceWindowType


class AssetMaintenanceWindow(BaseModel):
    """One planned downtime window for a managed asset."""

    __tablename__ = "asset_maintenance_windows"

    managed_asset_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("managed_assets.id", ondelete="CASCADE"), nullable=False, index=True
    )
    window_type: Mapped[MaintenanceWindowType] = mapped_column(String(16), index=True)
    starts_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    ends_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    recurrence_rule: Mapped[str | None] = mapped_column(String(255), default=None)
    approved: Mapped[bool] = mapped_column(Boolean, default=False)
    notify: Mapped[bool] = mapped_column(Boolean, default=True)


__all__ = ["AssetMaintenanceWindow"]
