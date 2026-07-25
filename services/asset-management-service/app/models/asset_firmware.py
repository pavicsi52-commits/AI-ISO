"""``asset_firmware`` table. Per docs/038 "FIRMWARE MANAGEMENT"
"Track": Firmware Version, Available Updates, Upgrade History,
Rollback History, Firmware Compliance, Vendor Recommendations. This
row is the asset's *current* firmware state; upgrade/rollback events
are recorded in :mod:`app.models.asset_change_history` (``event_type``
``"firmware_upgraded"``/``"firmware_rolled_back"``) rather than a
separate table, since docs/038's own DATABASE TABLES list names none.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from shared_core.database.base import BaseModel
from sqlalchemy import DateTime, ForeignKey, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.models.enums import ComplianceStatus


class AssetFirmware(BaseModel):
    """One managed asset's current firmware state."""

    __tablename__ = "asset_firmware"
    __table_args__ = (UniqueConstraint("managed_asset_id", name="uq_asset_firmware_managed_asset"),)

    managed_asset_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("managed_assets.id", ondelete="CASCADE"), nullable=False, index=True
    )
    current_version: Mapped[str] = mapped_column(String(64))
    available_version: Mapped[str | None] = mapped_column(String(64), default=None)
    compliance_status: Mapped[ComplianceStatus] = mapped_column(
        String(24), default=ComplianceStatus.UNKNOWN
    )
    vendor_recommendation: Mapped[str | None] = mapped_column(String(1024), default=None)
    last_checked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)


__all__ = ["AssetFirmware"]
