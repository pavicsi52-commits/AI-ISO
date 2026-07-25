"""``asset_labels`` table. Per docs/036 "LABELS": Key/Value Labels,
Namespaces, Selectors, Kubernetes Compatible Labels -- one row per
key/value pair, optionally grouped by :attr:`namespace` the same way
Kubernetes labels are (e.g. ``app.kubernetes.io/name``).
"""

from __future__ import annotations

import uuid

from shared_core.database.base import BaseModel
from sqlalchemy import ForeignKey, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column


class AssetLabel(BaseModel):
    """One key/value label on an asset."""

    __tablename__ = "asset_labels"
    __table_args__ = (UniqueConstraint("asset_id", "namespace", "key", name="uq_asset_label_key"),)

    asset_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("inventory_assets.id", ondelete="CASCADE"), nullable=False, index=True
    )
    namespace: Mapped[str | None] = mapped_column(String(255), default=None)
    key: Mapped[str] = mapped_column(String(255))
    value: Mapped[str] = mapped_column(String(1024))


__all__ = ["AssetLabel"]
