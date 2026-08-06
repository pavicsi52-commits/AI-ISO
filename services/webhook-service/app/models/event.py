"""``webhook_events`` -- one received or internally-raised event, before fan-out."""

from __future__ import annotations

from shared_core.database.base import BaseModel
from sqlalchemy import JSON, Index, String
from sqlalchemy.orm import Mapped, mapped_column

from app.models.enums import EventSource, WebhookKind


class WebhookEvent(BaseModel):
    """``webhook_events`` -- one event this service received or raised, pre-fan-out."""

    __tablename__ = "webhook_events"
    __table_args__ = (Index("ix_webhook_event_org_type", "organization_id", "event_type"),)

    kind: Mapped[WebhookKind] = mapped_column(String(32), index=True)
    source: Mapped[EventSource] = mapped_column(String(32), index=True)
    event_type: Mapped[str] = mapped_column(String(128))
    severity: Mapped[str | None] = mapped_column(String(16), default=None)
    status: Mapped[str | None] = mapped_column(String(32), default=None)
    tags: Mapped[list[str]] = mapped_column(JSON, default=list)
    labels: Mapped[dict[str, str]] = mapped_column(JSON, default=dict)
    payload: Mapped[dict[str, object]] = mapped_column(JSON, default=dict)
    headers: Mapped[dict[str, str]] = mapped_column(JSON, default=dict)
    idempotency_key: Mapped[str | None] = mapped_column(String(255), default=None, index=True)
    correlation_id: Mapped[str | None] = mapped_column(String(64), default=None, index=True)


__all__ = ["WebhookEvent"]
