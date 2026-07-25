"""``asset_tags`` table. Per docs/036 "TAGS": Multiple Tags, Bulk
Assignment, Filtering, Search, Inheritance.
"""

from __future__ import annotations

import uuid

from shared_core.database.base import BaseModel
from sqlalchemy import ForeignKey, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column


class AssetTag(BaseModel):
    """One tag assigned to an asset."""

    __tablename__ = "asset_tags"
    __table_args__ = (UniqueConstraint("asset_id", "label", name="uq_asset_tag_label"),)

    asset_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("inventory_assets.id", ondelete="CASCADE"), nullable=False, index=True
    )
    label: Mapped[str] = mapped_column(String(255), index=True)


__all__ = ["AssetTag"]
