"""``asset_vendors`` table -- the vendor/supplier registry backing
``managed_assets.vendor_id``, ``asset_contracts.vendor_id``, and
``asset_procurement.vendor_id``. Per docs/038 "PROCUREMENT" "Track":
Supplier.
"""

from __future__ import annotations

from shared_core.database.base import BaseModel
from sqlalchemy import String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column


class AssetVendor(BaseModel):
    """One vendor/supplier an organization tracks assets against."""

    __tablename__ = "asset_vendors"
    __table_args__ = (UniqueConstraint("organization_id", "name", name="uq_asset_vendor_org_name"),)

    name: Mapped[str] = mapped_column(String(255), index=True)
    contact_email: Mapped[str | None] = mapped_column(String(255), default=None)
    contact_phone: Mapped[str | None] = mapped_column(String(64), default=None)
    website: Mapped[str | None] = mapped_column(String(512), default=None)
    notes: Mapped[str | None] = mapped_column(String(2048), default=None)


__all__ = ["AssetVendor"]
