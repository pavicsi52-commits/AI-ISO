"""``notification_subscriptions`` -- one user's own opt-in to a topic.

Backs `shared_core.notifications.subscriptions.SubscriptionRegistry`'s
persisted equivalent. Per docs/055 "SUBSCRIPTIONS", ``target`` is
deliberately generic -- the same mechanism covers an event name, a
category, a role, a project, an organization, a free-form topic, or a
webhook endpoint, distinguished by :attr:`subscription_kind`.
"""

from __future__ import annotations

from shared_core.database.base import BaseModel
from sqlalchemy import String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.models.enums import SubscriptionKind


class NotificationSubscription(BaseModel):
    """``notification_subscriptions`` -- one user's opt-in to one topic."""

    __tablename__ = "notification_subscriptions"
    __table_args__ = (
        UniqueConstraint(
            "organization_id",
            "user_id",
            "subscription_kind",
            "target",
            name="uq_notification_subscription",
        ),
    )

    user_id: Mapped[str] = mapped_column(String(255), index=True)
    subscription_kind: Mapped[SubscriptionKind] = mapped_column(String(32), index=True)
    target: Mapped[str] = mapped_column(String(255), index=True)
    """What is being subscribed to -- an event name, category value,
    role name, project id, organization id, free-form topic, or webhook
    identifier, depending on :attr:`subscription_kind`."""

    webhook_url: Mapped[str | None] = mapped_column(String(2048), default=None)
    """Only meaningful for ``subscription_kind == WEBHOOK``."""


__all__ = ["NotificationSubscription"]
