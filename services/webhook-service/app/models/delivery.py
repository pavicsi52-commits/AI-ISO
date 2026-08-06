"""``webhook_deliveries`` and ``webhook_delivery_attempts``."""

from __future__ import annotations

import uuid
from datetime import datetime

from shared_core.database.base import BaseModel
from sqlalchemy import JSON, DateTime, Float, ForeignKey, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.models.enums import DeliveryMode, DeliveryStatus


class WebhookDelivery(BaseModel):
    """``webhook_deliveries`` -- one event's own delivery to one endpoint."""

    __tablename__ = "webhook_deliveries"
    __table_args__ = (
        Index("ix_webhook_delivery_org_status", "organization_id", "status"),
        Index("ix_webhook_delivery_endpoint", "endpoint_id"),
    )

    event_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("webhook_events.id", ondelete="CASCADE"), index=True
    )
    endpoint_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("webhook_endpoints.id", ondelete="CASCADE"), index=True
    )
    subscription_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("webhook_subscriptions.id", ondelete="SET NULL"), default=None
    )
    mode: Mapped[DeliveryMode] = mapped_column(String(16), default=DeliveryMode.QUEUED)
    status: Mapped[DeliveryStatus] = mapped_column(
        String(16), default=DeliveryStatus.QUEUED, index=True
    )
    priority: Mapped[int] = mapped_column(Integer, default=100)
    payload: Mapped[dict[str, object]] = mapped_column(JSON, default=dict)
    headers: Mapped[dict[str, str]] = mapped_column(JSON, default=dict)
    idempotency_key: Mapped[str | None] = mapped_column(String(255), default=None, index=True)
    attempt_count: Mapped[int] = mapped_column(Integer, default=0)
    max_attempts: Mapped[int] = mapped_column(Integer, default=8)
    scheduled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)
    delivered_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)
    acknowledged_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)
    last_error: Mapped[str | None] = mapped_column(Text, default=None)
    replay_job_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("webhook_replay_jobs.id", ondelete="SET NULL"), default=None
    )


class WebhookDeliveryAttempt(BaseModel):
    """``webhook_delivery_attempts`` -- one concrete HTTP attempt for one delivery."""

    __tablename__ = "webhook_delivery_attempts"
    __table_args__ = (Index("ix_webhook_attempt_delivery", "delivery_id"),)

    delivery_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("webhook_deliveries.id", ondelete="CASCADE"), index=True
    )
    endpoint_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("webhook_endpoints.id", ondelete="CASCADE"), index=True
    )
    """Denormalized from the parent delivery -- lets statistics rollup
    group by endpoint without a join, the same pattern every log-shaped
    table in this platform already uses (e.g. api-gateway-service's own
    ``ApiResponseLog.organization_id``)."""
    attempt_number: Mapped[int] = mapped_column(Integer)
    status_code: Mapped[int | None] = mapped_column(Integer, default=None)
    response_headers: Mapped[dict[str, str]] = mapped_column(JSON, default=dict)
    response_body: Mapped[str | None] = mapped_column(Text, default=None)
    latency_ms: Mapped[float | None] = mapped_column(Float, default=None)
    error: Mapped[str | None] = mapped_column(Text, default=None)
    attempted_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


__all__ = ["WebhookDelivery", "WebhookDeliveryAttempt"]
