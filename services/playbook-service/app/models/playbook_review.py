"""``playbook_reviews`` table. Per docs/041 "APPROVALS" "Support": Draft Review."""

from __future__ import annotations

import uuid
from datetime import datetime

from shared_core.database.base import BaseModel
from sqlalchemy import DateTime, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.models.enums import ReviewStatus


class PlaybookReview(BaseModel):
    """One draft-review step against a playbook (or one of its versions)."""

    __tablename__ = "playbook_reviews"

    playbook_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("playbooks.id", ondelete="CASCADE"), nullable=False, index=True
    )
    version_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("playbook_versions.id", ondelete="CASCADE"), default=None, index=True
    )
    reviewer_id: Mapped[uuid.UUID | None] = mapped_column(default=None)
    status: Mapped[ReviewStatus] = mapped_column(String(24), default=ReviewStatus.PENDING)
    comments: Mapped[str | None] = mapped_column(Text, default=None)
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)


__all__ = ["PlaybookReview"]
