"""``asset_types`` table -- a descriptive catalog entry for one
:class:`~app.models.enums.AssetType` value (display name, description,
icon), plus support for organization-defined custom types beyond the
44 built-in ones (docs/036's own "Custom Assets" entry in "SUPPORTED
ASSET TYPES"). :class:`~app.models.asset.Asset.asset_type` itself
always stores the fixed enum code; this table is reference/lookup data
describing it, not a foreign key target -- avoiding a hard dependency
that would block seeding assets before their catalog entry exists.
"""

from __future__ import annotations

import uuid

from shared_core.database.base import BaseModel
from sqlalchemy import Boolean, ForeignKey, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column


class AssetTypeDefinition(BaseModel):
    """One catalog entry describing an asset type."""

    __tablename__ = "asset_types"
    __table_args__ = (UniqueConstraint("organization_id", "code", name="uq_asset_type_code"),)

    code: Mapped[str] = mapped_column(String(64), index=True)
    name: Mapped[str] = mapped_column(String(255))
    description: Mapped[str | None] = mapped_column(String(2048), default=None)
    category_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("asset_categories.id", ondelete="SET NULL"), default=None
    )
    icon: Mapped[str | None] = mapped_column(String(128), default=None)
    is_system: Mapped[bool] = mapped_column(Boolean, default=False)


__all__ = ["AssetTypeDefinition"]
