"""SubscriptionService: idempotent subscribe, unsubscribe, and lookups.

Against real PostgreSQL, in a SAVEPOINT-isolated session per test.
"""

from __future__ import annotations

import pytest
from shared_core.exceptions.not_found import NotFoundError

from app.models.enums import SubscriptionKind
from app.services.subscription import SubscriptionService

pytestmark = pytest.mark.asyncio


class TestSubscribe:
    async def test_creates_a_new_subscription(
        self, subscription_service: SubscriptionService, organization_id
    ) -> None:
        created = await subscription_service.subscribe(
            organization_id, "user-1", SubscriptionKind.TOPIC, "outages"
        )
        assert created.user_id == "user-1"
        assert created.subscription_kind == SubscriptionKind.TOPIC
        assert created.target == "outages"

    async def test_is_idempotent_and_returns_the_existing_row(
        self, subscription_service: SubscriptionService, organization_id, subscriptions_repo
    ) -> None:
        first = await subscription_service.subscribe(
            organization_id, "user-1", SubscriptionKind.TOPIC, "outages"
        )
        second = await subscription_service.subscribe(
            organization_id, "user-1", SubscriptionKind.TOPIC, "outages"
        )
        assert first.id == second.id

        rows = await subscriptions_repo.list_for_user(organization_id, "user-1")
        assert len(rows) == 1

    async def test_accepts_a_webhook_url(
        self, subscription_service: SubscriptionService, organization_id
    ) -> None:
        created = await subscription_service.subscribe(
            organization_id,
            "user-1",
            SubscriptionKind.WEBHOOK,
            "endpoint-1",
            webhook_url="https://example.com/hook",
        )
        assert created.webhook_url == "https://example.com/hook"

    async def test_different_targets_create_distinct_rows(
        self, subscription_service: SubscriptionService, organization_id
    ) -> None:
        first = await subscription_service.subscribe(
            organization_id, "user-1", SubscriptionKind.TOPIC, "outages"
        )
        second = await subscription_service.subscribe(
            organization_id, "user-1", SubscriptionKind.TOPIC, "maintenance"
        )
        assert first.id != second.id


class TestUnsubscribe:
    async def test_removes_an_existing_subscription(
        self, subscription_service: SubscriptionService, organization_id
    ) -> None:
        await subscription_service.subscribe(
            organization_id, "user-1", SubscriptionKind.TOPIC, "outages"
        )
        await subscription_service.unsubscribe(
            organization_id, "user-1", SubscriptionKind.TOPIC, "outages"
        )
        remaining = await subscription_service.list_for_user(organization_id, "user-1")
        assert remaining == []

    async def test_raises_not_found_when_never_subscribed(
        self, subscription_service: SubscriptionService, organization_id
    ) -> None:
        with pytest.raises(NotFoundError):
            await subscription_service.unsubscribe(
                organization_id, "user-1", SubscriptionKind.TOPIC, "outages"
            )

    async def test_raises_not_found_for_a_different_target_of_the_same_kind(
        self, subscription_service: SubscriptionService, organization_id
    ) -> None:
        await subscription_service.subscribe(
            organization_id, "user-1", SubscriptionKind.TOPIC, "outages"
        )
        with pytest.raises(NotFoundError):
            await subscription_service.unsubscribe(
                organization_id, "user-1", SubscriptionKind.TOPIC, "maintenance"
            )


class TestListForUser:
    async def test_returns_every_subscription_the_user_holds(
        self, subscription_service: SubscriptionService, organization_id
    ) -> None:
        await subscription_service.subscribe(
            organization_id, "user-1", SubscriptionKind.TOPIC, "outages"
        )
        await subscription_service.subscribe(
            organization_id, "user-1", SubscriptionKind.ROLE, "admin"
        )
        await subscription_service.subscribe(
            organization_id, "user-2", SubscriptionKind.TOPIC, "outages"
        )

        found = await subscription_service.list_for_user(organization_id, "user-1")
        targets = {one.target for one in found}
        assert targets == {"outages", "admin"}

    async def test_returns_empty_list_for_a_user_with_no_subscriptions(
        self, subscription_service: SubscriptionService, organization_id
    ) -> None:
        found = await subscription_service.list_for_user(organization_id, "nobody")
        assert found == []


class TestSubscribersOf:
    async def test_returns_a_sorted_list_of_user_ids(
        self, subscription_service: SubscriptionService, organization_id
    ) -> None:
        await subscription_service.subscribe(
            organization_id, "zeta", SubscriptionKind.TOPIC, "outages"
        )
        await subscription_service.subscribe(
            organization_id, "alpha", SubscriptionKind.TOPIC, "outages"
        )

        subscribers = await subscription_service.subscribers_of(
            organization_id, SubscriptionKind.TOPIC, "outages"
        )
        assert subscribers == ["alpha", "zeta"]

    async def test_returns_empty_list_when_nobody_is_subscribed(
        self, subscription_service: SubscriptionService, organization_id
    ) -> None:
        subscribers = await subscription_service.subscribers_of(
            organization_id, SubscriptionKind.TOPIC, "nothing"
        )
        assert subscribers == []
