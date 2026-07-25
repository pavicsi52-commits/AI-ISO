"""``asset_history`` table -- a human-readable narrative timeline of
notable events on an asset (created, moved, owner changed, imported,
...), distinct from ``asset_versions``' full field snapshots and
``inventory_audit``'s privileged-action audit trail. The same
narrative-feed-vs-audit-trail split
``services/project-service``'s own ``project_activity``/``project_audit``
pair established.
"""

from __future__ import annotations

import uuid
from typing import Any

from shared_core.database.base import BaseModel
from sqlalchemy import JSON, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column


class AssetHistoryEntry(BaseModel):
    """One narrative timeline entry for an asset."""

    __tablename__ = "asset_history"

    asset_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("inventory_assets.id", ondelete="CASCADE"), nullable=False, index=True
    )
    actor_id: Mapped[uuid.UUID | None] = mapped_column(default=None)
    event_type: Mapped[str] = mapped_column(String(64))
    detail: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)


__all__ = ["AssetHistoryEntry"]
