"""``webhook_idempotency`` -- duplicate detection for caller-supplied keys."""

from __future__ import annotations

from datetime import datetime

from shared_core.database.base import BaseModel
from sqlalchemy import JSON, DateTime, Index, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.models.enums import IdempotencyStatus


class WebhookIdempotencyKey(BaseModel):
    """``webhook_idempotency`` -- one caller-supplied idempotency key's own settled result."""

    __tablename__ = "webhook_idempotency"
    __table_args__ = (
        UniqueConstraint("organization_id", "idempotency_key", name="uq_webhook_idempotency_key"),
        Index("ix_webhook_idempotency_expires_at", "expires_at"),
    )

    idempotency_key: Mapped[str] = mapped_column(String(255))
    status: Mapped[IdempotencyStatus] = mapped_column(
        String(16), default=IdempotencyStatus.PENDING, index=True
    )
    response_snapshot: Mapped[dict[str, object]] = mapped_column(JSON, default=dict)
    """The result recorded for this key -- replayed verbatim to a caller
    that retries with the same key instead of re-processing."""
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


__all__ = ["WebhookIdempotencyKey"]
