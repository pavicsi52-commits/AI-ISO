"""``asset_contacts`` table. Per docs/038 "OWNERSHIP" "Support": Vendor
Contact, Escalation Contact -- reachable contact persons, distinct
from :mod:`app.models.asset_owner`'s accountability roles.
"""

from __future__ import annotations

import uuid

from shared_core.database.base import BaseModel
from sqlalchemy import ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column

from app.models.enums import ContactRole


class AssetContact(BaseModel):
    """One reachable contact person associated with a managed asset."""

    __tablename__ = "asset_contacts"

    managed_asset_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("managed_assets.id", ondelete="CASCADE"), nullable=False, index=True
    )
    role: Mapped[ContactRole] = mapped_column(String(32), index=True)
    name: Mapped[str] = mapped_column(String(255))
    email: Mapped[str | None] = mapped_column(String(255), default=None)
    phone: Mapped[str | None] = mapped_column(String(64), default=None)


__all__ = ["AssetContact"]
