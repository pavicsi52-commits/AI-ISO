"""``asset_metadata`` table -- free-form key/value metadata on an
asset, distinct from ``asset_attributes``' schema-validated, typed
custom fields (see ``app/models/asset_custom_field.py``).
"""

from __future__ import annotations

import uuid

from shared_core.database.base import BaseModel
from sqlalchemy import ForeignKey, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column


class AssetMetadataEntry(BaseModel):
    """One free-form metadata key/value pair on an asset."""

    __tablename__ = "asset_metadata"
    __table_args__ = (UniqueConstraint("asset_id", "key", name="uq_asset_metadata_key"),)

    asset_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("inventory_assets.id", ondelete="CASCADE"), nullable=False, index=True
    )
    key: Mapped[str] = mapped_column(String(255))
    value: Mapped[str] = mapped_column(String(4096))


__all__ = ["AssetMetadataEntry"]
