"""``asset_maintenance`` table. Per docs/038 "MAINTENANCE" "Support":
Scheduled Maintenance, Emergency Maintenance, Preventive Maintenance,
Corrective Maintenance, Maintenance Calendar, Approval Workflow.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from shared_core.database.base import BaseModel
from sqlalchemy import DateTime, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column

from app.models.enums import MaintenanceStatus, MaintenanceType


class AssetMaintenance(BaseModel):
    """One maintenance activity scheduled or performed on a managed asset."""

    __tablename__ = "asset_maintenance"

    managed_asset_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("managed_assets.id", ondelete="CASCADE"), nullable=False, index=True
    )
    maintenance_type: Mapped[MaintenanceType] = mapped_column(String(16), index=True)
    status: Mapped[MaintenanceStatus] = mapped_column(
        String(16), default=MaintenanceStatus.SCHEDULED, index=True
    )
    description: Mapped[str] = mapped_column(String(2048))
    scheduled_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)
    approved_by: Mapped[uuid.UUID | None] = mapped_column(default=None)
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)


__all__ = ["AssetMaintenance"]
