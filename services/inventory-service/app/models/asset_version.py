"""``asset_versions`` table -- a full field-value snapshot of an asset
at one point in time, for diff/rollback -- the same "immutable
snapshot per change" shape
``services/secrets-management-service/app/models/secret_version.py``
uses, but capturing an asset's own mutable fields directly as JSON
(there being no encryption concern here) rather than a ciphertext blob.

"Who created this snapshot" is already
:class:`~shared_core.base.AuditMixin`'s own inherited ``created_by``
column via :class:`~shared_core.database.base.BaseModel` -- no
service-local column redeclares it.
"""

from __future__ import annotations

import uuid
from typing import Any

from shared_core.database.base import BaseModel
from sqlalchemy import JSON, ForeignKey, Integer
from sqlalchemy.orm import Mapped, mapped_column


class AssetVersion(BaseModel):
    """One historical snapshot of an asset's field values."""

    __tablename__ = "asset_versions"

    asset_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("inventory_assets.id", ondelete="CASCADE"), nullable=False, index=True
    )
    version_number: Mapped[int] = mapped_column(Integer)
    snapshot: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)


__all__ = ["AssetVersion"]
