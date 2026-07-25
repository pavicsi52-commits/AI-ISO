"""``asset_assignments`` table. Per docs/038 "ASSIGNMENTS" "Support":
Assign Asset, Reassign Asset, Bulk Assignment, Assignment History,
Assignment Approval, Temporary Assignment. Each assign/reassign creates
a new row rather than mutating one in place, so the table doubles as
its own "Assignment History".
"""

from __future__ import annotations

import uuid
from datetime import datetime

from shared_core.database.base import BaseModel
from sqlalchemy import DateTime, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column

from app.models.enums import AssignmentStatus, AssignmentType


class AssetAssignment(BaseModel):
    """One assignment of a managed asset to a principal."""

    __tablename__ = "asset_assignments"

    managed_asset_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("managed_assets.id", ondelete="CASCADE"), nullable=False, index=True
    )
    assignee_id: Mapped[uuid.UUID] = mapped_column(nullable=False, index=True)
    assignment_type: Mapped[AssignmentType] = mapped_column(
        String(16), default=AssignmentType.STANDARD
    )
    status: Mapped[AssignmentStatus] = mapped_column(
        String(24), default=AssignmentStatus.ACTIVE, index=True
    )
    assigned_by: Mapped[uuid.UUID | None] = mapped_column(default=None)
    assigned_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)
    returned_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)
    notes: Mapped[str | None] = mapped_column(String(1024), default=None)


__all__ = ["AssetAssignment"]
