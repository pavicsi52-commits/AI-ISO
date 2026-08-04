"""``change_conflicts`` -- two changes colliding over the same window, asset, or resource."""

from __future__ import annotations

import uuid
from datetime import datetime

from shared_core.database.base import BaseModel
from sqlalchemy import DateTime, ForeignKey, Index, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.models.enums import ConflictKind, ConflictStatus


class ChangeConflict(BaseModel):
    """``change_conflicts`` -- one detected collision between two changes.

    Directional but symmetric in meaning: *change_id* and
    *conflicting_change_id* both name real changes, and the pair is
    unique regardless of which one triggered detection -- a conflict
    between A and B is one fact, not two.
    """

    __tablename__ = "change_conflicts"
    __table_args__ = (
        UniqueConstraint(
            "organization_id",
            "change_id",
            "conflicting_change_id",
            "kind",
            name="uq_change_conflict",
        ),
        Index("ix_change_conflict_change", "organization_id", "change_id"),
        Index("ix_change_conflict_status", "organization_id", "status"),
    )

    change_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("change_requests.id", ondelete="CASCADE"), index=True
    )
    conflicting_change_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("change_requests.id", ondelete="CASCADE"), index=True
    )
    kind: Mapped[ConflictKind] = mapped_column(String(32), index=True)
    status: Mapped[ConflictStatus] = mapped_column(
        String(32), default=ConflictStatus.DETECTED, index=True
    )

    detail: Mapped[str] = mapped_column(Text)
    detected_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)

    resolved_by: Mapped[str | None] = mapped_column(String(255), default=None)
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)
    resolution_note: Mapped[str | None] = mapped_column(Text, default=None)


__all__ = ["ChangeConflict"]
