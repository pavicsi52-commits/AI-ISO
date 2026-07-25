"""``asset_attributes`` table -- one typed custom-field *value* on one
asset, against a definition in ``asset_custom_fields``. See that
module's own docstring for the schema/value split rationale.
:attr:`value` is stored as text regardless of the field's declared
type -- validation and type coercion happen at the service layer
against the field definition's ``validation_rule``, not via a
polymorphic set of typed columns.
"""

from __future__ import annotations

import uuid

from shared_core.database.base import BaseModel
from sqlalchemy import ForeignKey, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column


class AssetAttribute(BaseModel):
    """One custom attribute value on an asset."""

    __tablename__ = "asset_attributes"
    __table_args__ = (
        UniqueConstraint("asset_id", "custom_field_id", name="uq_asset_attribute_field"),
    )

    asset_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("inventory_assets.id", ondelete="CASCADE"), nullable=False, index=True
    )
    custom_field_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("asset_custom_fields.id", ondelete="CASCADE"), nullable=False, index=True
    )
    value: Mapped[str] = mapped_column(String(4096))


__all__ = ["AssetAttribute"]
