"""``asset_categories`` table -- the broadest tier of the three-level
Category > Class > Type classification hierarchy this service uses to
satisfy docs/036's "Asset Classification" acceptance criterion (e.g.
"Compute", "Network", "Storage", "Industrial", "Cloud", "Application").
:class:`~app.models.asset.Asset` itself always carries a fixed
:class:`~app.models.enums.AssetType` value; category/class are an
optional, organization-defined grouping layered on top.
"""

from __future__ import annotations

from shared_core.database.base import BaseModel
from sqlalchemy import String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column


class AssetCategory(BaseModel):
    """One broad asset category."""

    __tablename__ = "asset_categories"
    __table_args__ = (UniqueConstraint("organization_id", "name", name="uq_asset_category_name"),)

    name: Mapped[str] = mapped_column(String(255))
    description: Mapped[str | None] = mapped_column(String(2048), default=None)


__all__ = ["AssetCategory"]
