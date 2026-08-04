"""``change_post_reviews`` and ``change_post_review_action_items``.

The post-implementation review and its follow-up commitments -- an
action-item table sits alongside the one table docs/053 names
explicitly, mirroring Prompt 052's ``PostmortemActionItem`` for the same
reason: a review's "recommendations" are not commitments until someone
owns them and a due date exists to miss.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from shared_core.database.base import BaseModel
from sqlalchemy import DateTime, ForeignKey, Index, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.models.enums import ChangeTaskStatus, PirStatus


class ChangePostReview(BaseModel):
    """``change_post_reviews`` -- one change's post-implementation review."""

    __tablename__ = "change_post_reviews"
    __table_args__ = (
        UniqueConstraint("organization_id", "change_id", name="uq_change_post_review_change"),
    )

    change_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("change_requests.id", ondelete="CASCADE"), index=True
    )
    status: Mapped[PirStatus] = mapped_column(String(32), default=PirStatus.DRAFT, index=True)

    owner_id: Mapped[str | None] = mapped_column(String(255), default=None)

    implementation_summary: Mapped[str | None] = mapped_column(Text, default=None)
    objectives_achieved: Mapped[str | None] = mapped_column(Text, default=None)
    unexpected_issues: Mapped[str | None] = mapped_column(Text, default=None)
    lessons_learned: Mapped[str | None] = mapped_column(Text, default=None)
    risk_review: Mapped[str | None] = mapped_column(Text, default=None)
    recommendations: Mapped[str | None] = mapped_column(Text, default=None)

    approved_by: Mapped[str | None] = mapped_column(String(255), default=None)
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)


class ChangePostReviewActionItem(BaseModel):
    """``change_post_review_action_items`` -- one follow-up commitment from a PIR."""

    __tablename__ = "change_post_review_action_items"
    __table_args__ = (
        Index("ix_pir_action_item_review", "organization_id", "post_review_id"),
        Index("ix_pir_action_item_owner", "organization_id", "owner_id"),
    )

    post_review_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("change_post_reviews.id", ondelete="CASCADE"), index=True
    )
    title: Mapped[str] = mapped_column(String(512))
    description: Mapped[str | None] = mapped_column(Text, default=None)
    status: Mapped[ChangeTaskStatus] = mapped_column(
        String(32), default=ChangeTaskStatus.PENDING, index=True
    )
    owner_id: Mapped[str | None] = mapped_column(String(255), default=None, index=True)
    due_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)


__all__ = ["ChangePostReview", "ChangePostReviewActionItem"]
