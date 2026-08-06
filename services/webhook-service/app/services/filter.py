"""Webhook event-filter management (docs/057 "EVENT FILTERING")."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any
from uuid import UUID

from app.filters import engine as filters_engine
from app.models.enums import FilterMatchMode
from app.models.filter import WebhookFilter
from app.repositories.filter import WebhookFilterRepository


class FilterService:
    """A subscription's own event-filtering rule sets."""

    def __init__(self, filters: WebhookFilterRepository) -> None:
        self._filters = filters

    async def create(
        self,
        organization_id: UUID,
        *,
        subscription_id: UUID,
        name: str,
        rules: list[dict[str, Any]],
        match_mode: FilterMatchMode = FilterMatchMode.ALL,
    ) -> WebhookFilter:
        """Register a new filter rule set for one subscription."""
        return await self._filters.create(
            WebhookFilter(
                organization_id=organization_id,
                subscription_id=subscription_id,
                name=name,
                match_mode=match_mode,
                rules=list(rules),
            )
        )

    async def get(self, organization_id: UUID, filter_id: UUID) -> WebhookFilter:
        """One filter.

        Raises:
            NotFoundError: If it does not exist here.
        """
        return await self._filters.require_in_org(organization_id, filter_id)

    async def list_for_subscription(self, subscription_id: UUID) -> list[WebhookFilter]:
        """Every enabled filter attached to one subscription."""
        return await self._filters.list_for_subscription(subscription_id)

    async def passes(self, subscription_id: UUID, event_attributes: Mapping[str, Any]) -> bool:
        """Whether *event_attributes* passes every enabled filter on one subscription.

        A subscription with no filters configured always passes -- filters
        are an opt-in narrowing, not a default rejection.
        """
        filters = await self.list_for_subscription(subscription_id)
        return all(
            filters_engine.evaluate_rules(
                event_attributes, one.rules, match_mode=FilterMatchMode(one.match_mode)
            )
            for one in filters
        )


__all__ = ["FilterService"]
