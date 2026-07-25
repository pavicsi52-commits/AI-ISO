"""Subscription management. Per docs/033 "SUBSCRIPTIONS": Track Renewal,
Expiration, Billing Reference, Status.

No dedicated REST surface is named in docs/033's own endpoint list --
this service exists for programmatic completeness, the same scope
decision ``app/services/business_unit.py`` documents.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from datetime import datetime
from uuid import UUID

from shared_core.events.base import DomainEvent

from app.events.organization_events import SubscriptionChangedEvent
from app.models.enums import OrganizationActivityType, SubscriptionPlan, SubscriptionStatus
from app.models.organization_subscription import OrganizationSubscription
from app.repositories.organization_subscription import OrganizationSubscriptionRepository
from app.services.activity import OrganizationActivityService

EventPublisher = Callable[[DomainEvent], Awaitable[None]]


class OrganizationSubscriptionService:
    """Reads and updates an organization's subscription plan."""

    def __init__(
        self,
        subscriptions: OrganizationSubscriptionRepository,
        activity: OrganizationActivityService,
        *,
        publish_event: EventPublisher | None = None,
    ) -> None:
        self._subscriptions = subscriptions
        self._activity = activity
        self._publish_event = publish_event

    async def _publish(self, event: DomainEvent) -> None:
        if self._publish_event is not None:
            await self._publish_event(event)

    async def get_or_create(self, organization_id: UUID) -> OrganizationSubscription:
        """Return *organization_id*'s subscription, creating a trial if missing."""
        existing = await self._subscriptions.get_for_org(organization_id)
        if existing is not None:
            return existing
        return await self._subscriptions.create(
            OrganizationSubscription(organization_id=organization_id)
        )

    async def change_plan(
        self,
        organization_id: UUID,
        *,
        plan: SubscriptionPlan,
        status: SubscriptionStatus,
        billing_reference: str | None,
        renews_at: datetime | None,
        expires_at: datetime | None,
    ) -> OrganizationSubscription:
        """Change *organization_id*'s subscription plan ("SubscriptionChanged")."""
        subscription = await self.get_or_create(organization_id)
        subscription.plan = plan
        subscription.status = status
        subscription.billing_reference = billing_reference
        subscription.renews_at = renews_at
        subscription.expires_at = expires_at
        await self._activity.record(
            organization_id, activity_type=OrganizationActivityType.SUBSCRIPTION_CHANGED
        )
        await self._publish(
            SubscriptionChangedEvent(
                source_service="organization-service",
                payload={"organization_id": str(organization_id), "plan": str(plan)},
            )
        )
        return subscription


__all__ = ["OrganizationSubscriptionService"]
