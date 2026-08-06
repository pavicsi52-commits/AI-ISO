"""``webhook_filters`` -- event-filtering rules attached to a subscription."""

from __future__ import annotations

import uuid

from shared_core.database.base import BaseModel
from sqlalchemy import JSON, Boolean, ForeignKey, Index, String
from sqlalchemy.orm import Mapped, mapped_column

from app.models.enums import FilterMatchMode


class WebhookFilter(BaseModel):
    """``webhook_filters`` -- one subscription's own event-filtering rule set."""

    __tablename__ = "webhook_filters"
    __table_args__ = (Index("ix_webhook_filter_subscription", "subscription_id"),)

    subscription_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("webhook_subscriptions.id", ondelete="CASCADE"), index=True
    )
    name: Mapped[str] = mapped_column(String(128))
    match_mode: Mapped[FilterMatchMode] = mapped_column(String(8), default=FilterMatchMode.ALL)
    rules: Mapped[list[dict[str, object]]] = mapped_column(JSON, default=list)
    """Each rule: ``{"field": "severity", "operator": "eq", "value": "critical"}``.
    ``field`` reads from the event's own organization/project/event_type/
    severity/status/tags/labels/metadata; ``operator`` is one of
    ``eq``/``ne``/``in``/``not_in``/``contains``/``gt``/``lt``/``exists``.
    """
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)


__all__ = ["WebhookFilter"]
