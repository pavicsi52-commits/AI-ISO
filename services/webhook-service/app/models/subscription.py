"""``webhook_subscriptions`` -- binds an endpoint to event sources/types it wants."""

from __future__ import annotations

import uuid

from shared_core.database.base import BaseModel
from sqlalchemy import JSON, Boolean, ForeignKey, Index, String
from sqlalchemy.orm import Mapped, mapped_column

from app.models.enums import SubscriptionScope


class WebhookSubscription(BaseModel):
    """``webhook_subscriptions`` -- one endpoint's own subscription to a slice of events."""

    __tablename__ = "webhook_subscriptions"
    __table_args__ = (Index("ix_webhook_subscription_org_scope", "organization_id", "scope"),)

    endpoint_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("webhook_endpoints.id", ondelete="CASCADE"), index=True
    )
    scope: Mapped[SubscriptionScope] = mapped_column(String(16), index=True)
    scope_reference: Mapped[str | None] = mapped_column(String(255), default=None)
    """The scope's own target -- a project id, a role name, a user id, a topic
    name, an event-type pattern, or a resource id, depending on ``scope``.
    ``None`` only for ``WILDCARD`` (matches every event)."""
    event_types: Mapped[list[str]] = mapped_column(JSON, default=list)
    """Event types this subscription matches; empty means every type under *scope*."""
    condition_expression: Mapped[str | None] = mapped_column(String(1024), default=None)
    """A boolean expression evaluated by ``app/filters/engine.py`` -- only
    used when ``scope`` is ``CONDITIONAL``."""
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)


__all__ = ["WebhookSubscription"]
