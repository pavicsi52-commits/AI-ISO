"""``asset_warranty`` table. Per docs/038 "WARRANTY" "Track": Warranty
Provider, Warranty Number, Coverage, Start Date, End Date, Expiration
Alerts, Renewal Status, Warranty Claims. A renewal inserts a new row
rather than mutating the prior period, so the table also serves as its
own warranty-period history; :attr:`claims` is a lightweight embedded
list (date/description/outcome) since docs/038 names no dedicated
claims table.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from shared_core.database.base import BaseModel
from sqlalchemy import JSON, Boolean, DateTime, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column

from app.models.enums import RenewalStatus


class AssetWarranty(BaseModel):
    """One warranty coverage period for a managed asset."""

    __tablename__ = "asset_warranty"

    managed_asset_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("managed_assets.id", ondelete="CASCADE"), nullable=False, index=True
    )
    provider: Mapped[str] = mapped_column(String(255))
    warranty_number: Mapped[str | None] = mapped_column(String(128), default=None)
    coverage: Mapped[str | None] = mapped_column(String(1024), default=None)
    start_date: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    end_date: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    expiration_alert_sent: Mapped[bool] = mapped_column(Boolean, default=False)
    renewal_status: Mapped[RenewalStatus] = mapped_column(
        String(16), default=RenewalStatus.NOT_RENEWED
    )
    claims: Mapped[list[dict[str, Any]]] = mapped_column(JSON, default=list)


__all__ = ["AssetWarranty"]
