"""``asset_owners`` table. Per docs/038 "OWNERSHIP" "Support": Business
Owner, Technical Owner, Application Owner, Infrastructure Owner,
Department, Support Team (the accountability *roles*; reachable
contacts are :mod:`app.models.asset_contact`). One asset may have up
to one owner per :class:`~app.models.enums.OwnerRole`; "Ownership
History"/"Transfer Ownership" are served by superseding the row
(deleted, per :class:`~shared_core.base.BaseEntityMixin`'s soft
delete) and inserting a new one, keeping every prior holder queryable.
"""

from __future__ import annotations

import uuid

from shared_core.database.base import BaseModel
from sqlalchemy import ForeignKey, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.models.enums import OwnerRole


class AssetOwner(BaseModel):
    """One ownership-role assignment on a managed asset."""

    __tablename__ = "asset_owners"
    __table_args__ = (UniqueConstraint("managed_asset_id", "role", name="uq_asset_owner_role"),)

    managed_asset_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("managed_assets.id", ondelete="CASCADE"), nullable=False, index=True
    )
    role: Mapped[OwnerRole] = mapped_column(String(32), index=True)
    principal_id: Mapped[uuid.UUID | None] = mapped_column(default=None)
    name: Mapped[str | None] = mapped_column(String(255), default=None)


__all__ = ["AssetOwner"]
