"""``asset_owners`` table. Per docs/036 "OWNERSHIP": Business Owner,
Technical Owner, Support Team, Vendor, Department (Organization/Project
are already the inherited tenant-scope columns every AI-IOS entity
carries). One asset may have up to one owner per :class:`~app.models
.enums.OwnerType` role -- :attr:`principal_id` for roles that map to a
platform user, :attr:`name` for roles that don't (Vendor, Department).
"""

from __future__ import annotations

import uuid

from shared_core.database.base import BaseModel
from sqlalchemy import ForeignKey, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.models.enums import OwnerType


class AssetOwner(BaseModel):
    """One ownership-role assignment on an asset."""

    __tablename__ = "asset_owners"
    __table_args__ = (UniqueConstraint("asset_id", "owner_type", name="uq_asset_owner_role"),)

    asset_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("inventory_assets.id", ondelete="CASCADE"), nullable=False, index=True
    )
    owner_type: Mapped[OwnerType] = mapped_column(String(24), index=True)
    principal_id: Mapped[uuid.UUID | None] = mapped_column(default=None)
    name: Mapped[str | None] = mapped_column(String(255), default=None)


__all__ = ["AssetOwner"]
