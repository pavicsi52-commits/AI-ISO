"""Notification subscriptions.

The persisted equivalent of `shared_core.notifications.subscriptions
.SubscriptionRegistry`, per-organization. ``subscribe`` is idempotent --
subscribing twice to the same ``(user_id, subscription_kind, target)``
returns the existing row rather than raising, matching
`SubscriptionRegistry.subscribe`'s own set-based idempotency.
"""

from __future__ import annotations

from uuid import UUID

from shared_core.exceptions.not_found import NotFoundError

from app.models.enums import SubscriptionKind
from app.models.subscription import NotificationSubscription
from app.repositories.subscription import NotificationSubscriptionRepository


class SubscriptionService:
    """Users' own opt-ins to events, categories, roles, projects, organizations, and topics."""

    def __init__(self, subscriptions: NotificationSubscriptionRepository) -> None:
        self._subscriptions = subscriptions

    async def subscribe(
        self,
        organization_id: UUID,
        user_id: str,
        subscription_kind: SubscriptionKind,
        target: str,
        *,
        webhook_url: str | None = None,
    ) -> NotificationSubscription:
        """Subscribe *user_id* to *target*, or return the existing subscription."""
        existing = await self._subscriptions.find(
            organization_id, user_id, subscription_kind, target
        )
        if existing is not None:
            return existing
        return await self._subscriptions.create(
            NotificationSubscription(
                organization_id=organization_id,
                user_id=user_id,
                subscription_kind=subscription_kind,
                target=target,
                webhook_url=webhook_url,
            )
        )

    async def unsubscribe(
        self, organization_id: UUID, user_id: str, subscription_kind: SubscriptionKind, target: str
    ) -> None:
        """Remove a subscription.

        Raises:
            NotFoundError: If *user_id* is not currently subscribed to *target*.
        """
        existing = await self._subscriptions.find(
            organization_id, user_id, subscription_kind, target
        )
        if existing is None:
            raise NotFoundError(f"{user_id!r} is not subscribed to {target!r}.")
        await self._subscriptions.delete(existing.id)

    async def list_for_user(
        self, organization_id: UUID, user_id: str
    ) -> list[NotificationSubscription]:
        """Every subscription *user_id* currently holds."""
        return await self._subscriptions.list_for_user(organization_id, user_id)

    async def subscribers_of(
        self, organization_id: UUID, subscription_kind: SubscriptionKind, target: str
    ) -> list[str]:
        """Every user id subscribed to *target* ("Broadcast Groups")."""
        return await self._subscriptions.list_subscribers(
            organization_id, subscription_kind, target
        )


__all__ = ["SubscriptionService"]
