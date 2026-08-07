"""``plugin_reviews`` and ``plugin_ratings``."""

from __future__ import annotations

import uuid
from datetime import datetime

from shared_core.database.base import BaseModel
from sqlalchemy import (
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.models.enums import ReviewStatus


class PluginReview(BaseModel):
    """``plugin_reviews`` -- one public star-rating + text review.

    Genuinely new -- not modeled on ``playbook-service``'s
    ``PlaybookReview``, which is an internal draft-approval workflow
    step (status/reviewer_id/comments on a *pending* playbook version),
    not a public post-publish rating system. No precedent for this
    shape exists anywhere in the monorepo.
    """

    __tablename__ = "plugin_reviews"
    __table_args__ = (
        UniqueConstraint("plugin_id", "reviewer_id", name="uq_plugin_review_reviewer"),
        Index("ix_plugin_review_status", "status"),
    )

    plugin_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("plugins.id", ondelete="CASCADE"), index=True
    )
    reviewer_id: Mapped[str] = mapped_column(String(128))
    rating: Mapped[int] = mapped_column(Integer)
    """1-5 stars, enforced by ``PluginReviewService`` at the service layer."""
    title: Mapped[str | None] = mapped_column(String(255), default=None)
    body: Mapped[str | None] = mapped_column(Text, default=None)
    installed_version_number: Mapped[str | None] = mapped_column(String(32), default=None)
    verified_install: Mapped[bool] = mapped_column(Boolean, default=False)
    status: Mapped[ReviewStatus] = mapped_column(
        String(16), default=ReviewStatus.PUBLISHED, index=True
    )
    publisher_response: Mapped[str | None] = mapped_column(Text, default=None)
    publisher_responded_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), default=None
    )
    flagged_reason: Mapped[str | None] = mapped_column(Text, default=None)
    moderated_by: Mapped[str | None] = mapped_column(String(128), default=None)
    moderated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)


class PluginRating(BaseModel):
    """``plugin_ratings`` -- one plugin's own rolled-up rating aggregate.

    Kept separate from ``PluginReview`` (the raw per-user rows) so the
    aggregate can be recomputed cheaply by a worker sweep without
    scanning every review row inline on each read.
    """

    __tablename__ = "plugin_ratings"
    __table_args__ = (UniqueConstraint("plugin_id", name="uq_plugin_rating_plugin"),)

    plugin_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("plugins.id", ondelete="CASCADE"), index=True
    )
    average_rating: Mapped[float] = mapped_column(Float, default=0.0)
    review_count: Mapped[int] = mapped_column(Integer, default=0)
    rating_1_count: Mapped[int] = mapped_column(Integer, default=0)
    rating_2_count: Mapped[int] = mapped_column(Integer, default=0)
    rating_3_count: Mapped[int] = mapped_column(Integer, default=0)
    rating_4_count: Mapped[int] = mapped_column(Integer, default=0)
    rating_5_count: Mapped[int] = mapped_column(Integer, default=0)
    recalculated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)


__all__ = ["PluginRating", "PluginReview"]
