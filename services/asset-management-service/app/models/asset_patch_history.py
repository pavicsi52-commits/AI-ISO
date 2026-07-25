"""``asset_patch_history`` table. Per docs/038 "SOFTWARE MANAGEMENT"
"Track": Patches, Security Updates.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from shared_core.database.base import BaseModel
from sqlalchemy import DateTime, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column

from app.models.enums import AuditOutcome


class AssetPatchHistoryEntry(BaseModel):
    """One patch or security update applied to a managed asset."""

    __tablename__ = "asset_patch_history"

    managed_asset_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("managed_assets.id", ondelete="CASCADE"), nullable=False, index=True
    )
    software_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("asset_software.id", ondelete="SET NULL"), default=None
    )
    patch_name: Mapped[str] = mapped_column(String(255))
    applied_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    outcome: Mapped[AuditOutcome] = mapped_column(String(16), default=AuditOutcome.SUCCESS)
    notes: Mapped[str | None] = mapped_column(String(1024), default=None)


__all__ = ["AssetPatchHistoryEntry"]
