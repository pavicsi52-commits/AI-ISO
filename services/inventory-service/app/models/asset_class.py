"""``asset_classes`` table -- the middle tier of the Category > Class >
Type classification hierarchy (e.g. within "Compute": "Server", "VM",
"Container"). See ``app/models/asset_category.py``'s own docstring.
"""

from __future__ import annotations

import uuid

from shared_core.database.base import BaseModel
from sqlalchemy import ForeignKey, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column


class AssetClass(BaseModel):
    """One asset class, nested under a category."""

    __tablename__ = "asset_classes"
    __table_args__ = (
        UniqueConstraint("category_id", "name", name="uq_asset_class_name_per_category"),
    )

    category_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("asset_categories.id", ondelete="CASCADE"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String(255))
    description: Mapped[str | None] = mapped_column(String(2048), default=None)


__all__ = ["AssetClass"]
