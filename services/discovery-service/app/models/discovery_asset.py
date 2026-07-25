"""``discovery_assets`` table -- one discovered infrastructure asset,
prior to (or pending) synchronization into the Inventory Service.
"""

from __future__ import annotations

import uuid
from typing import Any

from shared_core.database.base import BaseModel
from sqlalchemy import JSON, Boolean, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column

from app.models.enums import AssetClassification, SyncStatus


class DiscoveryAsset(BaseModel):
    """One asset identified by a discovery job."""

    __tablename__ = "discovery_assets"

    job_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("discovery_jobs.id", ondelete="CASCADE"), index=True
    )
    result_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("discovery_results.id", ondelete="CASCADE"), index=True
    )
    name: Mapped[str] = mapped_column(String(255), index=True)
    asset_type: Mapped[str] = mapped_column(String(64), index=True)
    classification: Mapped[AssetClassification] = mapped_column(
        String(24), default=AssetClassification.CUSTOM, index=True
    )
    fingerprint: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    synced_to_inventory: Mapped[bool] = mapped_column(Boolean, default=False)
    sync_status: Mapped[SyncStatus] = mapped_column(
        String(16), default=SyncStatus.PENDING, index=True
    )
    inventory_asset_id: Mapped[uuid.UUID | None] = mapped_column(default=None)


__all__ = ["DiscoveryAsset"]
