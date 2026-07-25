"""``inventory_audit`` table -- privileged-action audit trail. Per
docs/036 "AUDIT": Asset Creation, Updates, Deletion, Imports, Exports,
Relationship Changes, Ownership Changes, Status Changes, Metadata
Changes, Administrative Actions.
"""

from __future__ import annotations

import uuid
from typing import Any

from shared_core.database.base import BaseModel
from sqlalchemy import JSON, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column

from app.models.enums import AuditOutcome


class InventoryAuditEntry(BaseModel):
    """One privileged/administrative action recorded against an asset."""

    __tablename__ = "inventory_audit"

    asset_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("inventory_assets.id", ondelete="CASCADE"), default=None, index=True
    )
    actor_id: Mapped[uuid.UUID | None] = mapped_column(default=None)
    action: Mapped[str] = mapped_column(String(64))
    outcome: Mapped[AuditOutcome] = mapped_column(String(16), default=AuditOutcome.SUCCESS)
    reason: Mapped[str] = mapped_column(String(1024), default="")
    before: Mapped[dict[str, Any] | None] = mapped_column(JSON, default=None)
    after: Mapped[dict[str, Any] | None] = mapped_column(JSON, default=None)


__all__ = ["InventoryAuditEntry"]
