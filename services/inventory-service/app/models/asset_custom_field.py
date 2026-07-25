"""``asset_custom_fields`` table -- a per-organization custom field
*definition* (name, type, validation rule). Per docs/036 "CUSTOM
ATTRIBUTES": Dynamic Fields, Schemas, Validation, Typed Values. The
actual per-asset *values* against a definition live in
``asset_attributes`` (``app/models/asset_attribute.py``) -- the same
"schema table" / "value table" split
``services/rbac-service``'s own dynamic-permission-schema precedent
established, so a field's type/validation rule is defined once and
enforced consistently across every asset using it.
"""

from __future__ import annotations

from typing import Any

from shared_core.database.base import BaseModel
from sqlalchemy import JSON, Boolean, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.models.enums import CustomFieldType


class AssetCustomField(BaseModel):
    """One custom field definition available to assets in an organization."""

    __tablename__ = "asset_custom_fields"
    __table_args__ = (
        UniqueConstraint("organization_id", "name", name="uq_asset_custom_field_name"),
    )

    name: Mapped[str] = mapped_column(String(255))
    description: Mapped[str | None] = mapped_column(String(2048), default=None)
    field_type: Mapped[CustomFieldType] = mapped_column(String(16), default=CustomFieldType.STRING)
    is_required: Mapped[bool] = mapped_column(Boolean, default=False)
    validation_rule: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)


__all__ = ["AssetCustomField"]
