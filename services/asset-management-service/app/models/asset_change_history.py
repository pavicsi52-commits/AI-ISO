"""``asset_change_history`` table -- a human-readable narrative
timeline of notable events on a managed asset (status changed, owner
transferred, lifecycle action applied, ...), serving docs/038
"LIFECYCLE MANAGEMENT" "Lifecycle Audit" alongside general change
tracking. The same narrative-feed-vs-audit-trail split
``inventory-service``'s own ``asset_history``/``inventory_audit`` pair
established (privileged/administrative actions are
:mod:`app.models.asset_audit`).
"""

from __future__ import annotations

import uuid
from typing import Any

from shared_core.database.base import BaseModel
from sqlalchemy import JSON, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column


class AssetChangeHistoryEntry(BaseModel):
    """One narrative timeline entry for a managed asset."""

    __tablename__ = "asset_change_history"

    managed_asset_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("managed_assets.id", ondelete="CASCADE"), nullable=False, index=True
    )
    actor_id: Mapped[uuid.UUID | None] = mapped_column(default=None)
    event_type: Mapped[str] = mapped_column(String(64))
    detail: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)


__all__ = ["AssetChangeHistoryEntry"]
