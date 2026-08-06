"""``webhook_retry_queue`` and ``webhook_dead_letters``."""

from __future__ import annotations

import uuid
from datetime import datetime

from shared_core.database.base import BaseModel
from sqlalchemy import Boolean, DateTime, ForeignKey, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.models.enums import RetryBackoffStrategy


class WebhookRetryQueueEntry(BaseModel):
    """``webhook_retry_queue`` -- one delivery's own next scheduled retry."""

    __tablename__ = "webhook_retry_queue"
    __table_args__ = (Index("ix_webhook_retry_due", "next_attempt_at"),)

    delivery_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("webhook_deliveries.id", ondelete="CASCADE"), unique=True, index=True
    )
    attempt_number: Mapped[int] = mapped_column(Integer)
    backoff_strategy: Mapped[RetryBackoffStrategy] = mapped_column(
        String(16), default=RetryBackoffStrategy.EXPONENTIAL
    )
    next_attempt_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    last_error: Mapped[str | None] = mapped_column(Text, default=None)


class WebhookDeadLetter(BaseModel):
    """``webhook_dead_letters`` -- a delivery that exhausted its own retry policy."""

    __tablename__ = "webhook_dead_letters"
    __table_args__ = (Index("ix_webhook_dead_letter_org", "organization_id"),)

    delivery_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("webhook_deliveries.id", ondelete="CASCADE"), unique=True, index=True
    )
    endpoint_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("webhook_endpoints.id", ondelete="CASCADE"), index=True
    )
    attempt_count: Mapped[int] = mapped_column(Integer)
    last_error: Mapped[str | None] = mapped_column(Text, default=None)
    dead_lettered_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    replayed: Mapped[bool] = mapped_column(Boolean, default=False)


__all__ = ["WebhookDeadLetter", "WebhookRetryQueueEntry"]
