"""Webhook subscription management (docs/057 "SUBSCRIPTIONS")."""

from __future__ import annotations

from typing import Any
from uuid import UUID

from app.models.enums import SubscriptionScope
from app.models.subscription import WebhookSubscription
from app.repositories.subscription import WebhookSubscriptionRepository
from app.subscriptions import engine as subscriptions_engine

_EDITABLE_FIELDS = frozenset({"scope_reference", "event_types", "condition_expression", "enabled"})


class SubscriptionService:
    """An endpoint's own subscriptions to a slice of events."""

    def __init__(self, subscriptions: WebhookSubscriptionRepository) -> None:
        self._subscriptions = subscriptions

    async def create(
        self,
        organization_id: UUID,
        *,
        endpoint_id: UUID,
        scope: SubscriptionScope,
        scope_reference: str | None = None,
        event_types: list[str] | None = None,
        condition_expression: str | None = None,
    ) -> WebhookSubscription:
        """Register a new subscription."""
        return await self._subscriptions.create(
            WebhookSubscription(
                organization_id=organization_id,
                endpoint_id=endpoint_id,
                scope=scope,
                scope_reference=scope_reference,
                event_types=list(event_types or []),
                condition_expression=condition_expression,
            )
        )

    async def get(self, organization_id: UUID, subscription_id: UUID) -> WebhookSubscription:
        """One subscription.

        Raises:
            NotFoundError: If it does not exist here.
        """
        return await self._subscriptions.require_in_org(organization_id, subscription_id)

    async def list_subscriptions(self, organization_id: UUID) -> list[WebhookSubscription]:
        """Subscriptions in this organization."""
        return await self._subscriptions.list_for_org(organization_id)

    async def update(
        self, organization_id: UUID, subscription_id: UUID, **fields: Any
    ) -> WebhookSubscription:
        """Edit a subscription's editable fields."""
        stored = await self._subscriptions.require_in_org(organization_id, subscription_id)
        for field, value in fields.items():
            if field in _EDITABLE_FIELDS and value is not None:
                setattr(stored, field, value)
        return await self._subscriptions.update(stored)

    async def delete(self, organization_id: UUID, subscription_id: UUID) -> None:
        """Remove a subscription."""
        stored = await self._subscriptions.require_in_org(organization_id, subscription_id)
        await self._subscriptions.delete(stored.id)

    async def resolve_matching(
        self, organization_id: UUID, event: subscriptions_engine.EventContext
    ) -> list[WebhookSubscription]:
        """Every enabled subscription in this organization whose own scope matches *event*."""
        candidates = await self._subscriptions.list_enabled_for_org(organization_id)
        matching_ids = {
            candidate.id
            for candidate in subscriptions_engine.matching_subscriptions(
                [
                    subscriptions_engine.SubscriptionCandidate(
                        id=str(row.id),
                        scope=SubscriptionScope(row.scope),
                        scope_reference=row.scope_reference,
                        event_types=tuple(row.event_types),
                        enabled=row.enabled,
                    )
                    for row in candidates
                ],
                event,
            )
        }
        return [row for row in candidates if str(row.id) in matching_ids]


__all__ = ["SubscriptionService"]
