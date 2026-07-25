"""``asset_discovery_links`` table -- correlates an asset with the
external discovery-source record that produced or last confirmed it.
Per docs/036 "INVENTORY SYNCHRONIZATION": "Discovery Updates". The
discovery engine that populates these is explicitly out of scope
("DO NOT IMPLEMENT": "Discovery Engine") -- this only stores the
correlation an external caller reports.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from shared_core.database.base import BaseModel
from sqlalchemy import DateTime, ForeignKey, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.models.enums import DiscoverySource


class AssetDiscoveryLink(BaseModel):
    """One correlation between an asset and an external discovery record."""

    __tablename__ = "asset_discovery_links"
    __table_args__ = (
        UniqueConstraint("source", "external_id", name="uq_asset_discovery_link_external_id"),
    )

    asset_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("inventory_assets.id", ondelete="CASCADE"), nullable=False, index=True
    )
    source: Mapped[DiscoverySource] = mapped_column(String(24), index=True)
    external_id: Mapped[str] = mapped_column(String(255), index=True)
    last_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


__all__ = ["AssetDiscoveryLink"]
