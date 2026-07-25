"""``asset_contacts`` table -- reachable contact persons for an asset
(distinct from ``asset_owners``' accountability *roles*: a support
team's own on-call contact, a vendor's account representative, etc.).
"""

from __future__ import annotations

import uuid

from shared_core.database.base import BaseModel
from sqlalchemy import ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column


class AssetContact(BaseModel):
    """One contact person associated with an asset."""

    __tablename__ = "asset_contacts"

    asset_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("inventory_assets.id", ondelete="CASCADE"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String(255))
    email: Mapped[str | None] = mapped_column(String(255), default=None)
    phone: Mapped[str | None] = mapped_column(String(64), default=None)
    role: Mapped[str | None] = mapped_column(String(128), default=None)


__all__ = ["AssetContact"]
