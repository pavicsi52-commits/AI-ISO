"""``asset_audit`` table -- privileged-action audit trail. Per
docs/038 "AUDIT": Ownership Changes, Assignments, Maintenance,
Compliance Changes, Risk Updates, Lifecycle Events, Financial Updates,
Administrative Operations.
"""

from __future__ import annotations

import uuid
from typing import Any

from shared_core.database.base import BaseModel
from sqlalchemy import JSON, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column

from app.models.enums import AuditOutcome


class AssetAuditEntry(BaseModel):
    """One privileged/administrative action recorded against a managed asset."""

    __tablename__ = "asset_audit"

    managed_asset_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("managed_assets.id", ondelete="CASCADE"), default=None, index=True
    )
    actor_id: Mapped[uuid.UUID | None] = mapped_column(default=None)
    action: Mapped[str] = mapped_column(String(64))
    outcome: Mapped[AuditOutcome] = mapped_column(String(16), default=AuditOutcome.SUCCESS)
    reason: Mapped[str] = mapped_column(String(1024), default="")
    before: Mapped[dict[str, Any] | None] = mapped_column(JSON, default=None)
    after: Mapped[dict[str, Any] | None] = mapped_column(JSON, default=None)


__all__ = ["AssetAuditEntry"]
