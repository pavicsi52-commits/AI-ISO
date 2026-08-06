"""``webhook_replay_jobs`` -- a request to redeliver a past slice of events."""

from __future__ import annotations

import uuid
from datetime import datetime

from shared_core.database.base import BaseModel
from sqlalchemy import JSON, Boolean, DateTime, ForeignKey, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.models.enums import ReplayScope, ReplayStatus


class WebhookReplayJob(BaseModel):
    """``webhook_replay_jobs`` -- one request to redeliver a past slice of events."""

    __tablename__ = "webhook_replay_jobs"
    __table_args__ = (Index("ix_webhook_replay_org_status", "organization_id", "status"),)

    scope: Mapped[ReplayScope] = mapped_column(String(16))
    event_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("webhook_events.id", ondelete="SET NULL"), default=None
    )
    endpoint_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("webhook_endpoints.id", ondelete="SET NULL"), default=None
    )
    subscription_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("webhook_subscriptions.id", ondelete="SET NULL"), default=None
    )
    date_range_start: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)
    date_range_end: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)
    status: Mapped[ReplayStatus] = mapped_column(
        String(16), default=ReplayStatus.PENDING, index=True
    )
    dry_run: Mapped[bool] = mapped_column(Boolean, default=False)
    matched_count: Mapped[int] = mapped_column(Integer, default=0)
    replayed_count: Mapped[int] = mapped_column(Integer, default=0)
    failed_count: Mapped[int] = mapped_column(Integer, default=0)
    requested_by: Mapped[str | None] = mapped_column(String(128), default=None)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)
    error: Mapped[str | None] = mapped_column(Text, default=None)
    preview: Mapped[dict[str, object]] = mapped_column(JSON, default=dict)


__all__ = ["WebhookReplayJob"]
