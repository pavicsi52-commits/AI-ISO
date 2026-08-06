"""``webhook_endpoints`` -- a registered outgoing-delivery target."""

from __future__ import annotations

from datetime import datetime

from shared_core.database.base import BaseModel
from sqlalchemy import JSON, Boolean, DateTime, Float, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.models.enums import EndpointStatus, WebhookAuthMethod, WebhookKind


class WebhookEndpoint(BaseModel):
    """``webhook_endpoints`` -- one caller-registered outgoing delivery target."""

    __tablename__ = "webhook_endpoints"
    __table_args__ = (Index("ix_webhook_endpoint_org_status", "organization_id", "status"),)

    name: Mapped[str] = mapped_column(String(128))
    description: Mapped[str | None] = mapped_column(Text, default=None)
    url: Mapped[str] = mapped_column(String(2048))
    kind: Mapped[WebhookKind] = mapped_column(String(32), default=WebhookKind.OUTGOING, index=True)
    auth_method: Mapped[WebhookAuthMethod] = mapped_column(
        String(32), default=WebhookAuthMethod.HMAC_SHA256
    )
    headers: Mapped[dict[str, str]] = mapped_column(JSON, default=dict)
    status: Mapped[EndpointStatus] = mapped_column(
        String(16), default=EndpointStatus.ACTIVE, index=True
    )
    metadata_: Mapped[dict[str, object]] = mapped_column("metadata", JSON, default=dict)
    owner_id: Mapped[str | None] = mapped_column(String(128), default=None)
    timeout_seconds: Mapped[float | None] = mapped_column(Float, default=None)
    max_attempts: Mapped[int | None] = mapped_column(Integer, default=None)
    backoff_strategy: Mapped[str | None] = mapped_column(String(16), default=None)
    consecutive_failures: Mapped[int] = mapped_column(Integer, default=0)
    last_delivered_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), default=None
    )
    last_failed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)


__all__ = ["WebhookEndpoint"]
