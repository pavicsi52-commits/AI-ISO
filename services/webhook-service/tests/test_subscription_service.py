"""SubscriptionService and WebhookSubscriptionRepository: registration, editing, resolution.

Against real PostgreSQL, in a SAVEPOINT-isolated session per test.

``resolve_matching`` is the integration point between this service and the
pure ``app.subscriptions.engine`` module (a different agent's own dedicated
scope, tested exhaustively in isolation there): these tests prove the
service correctly assembles ``SubscriptionCandidate``s from real persisted
rows and returns the actual matching ``WebhookSubscription`` rows -- not the
matching algorithm's own behaviour in depth.
"""

from __future__ import annotations

import uuid

import pytest
from shared_core.exceptions.not_found import NotFoundError

from app.models.enums import SubscriptionScope
from app.repositories.subscription import WebhookSubscriptionRepository
from app.services.subscription import SubscriptionService
from app.subscriptions.engine import EventContext


class TestCreate:
    async def test_creates_with_defaults(
        self, subscription_service: SubscriptionService, organization_id: uuid.UUID, make_endpoint
    ) -> None:
        endpoint = await make_endpoint()
        created = await subscription_service.create(
            organization_id, endpoint_id=endpoint.id, scope=SubscriptionScope.WILDCARD
        )
        assert created.endpoint_id == endpoint.id
        assert created.scope == SubscriptionScope.WILDCARD
        assert created.scope_reference is None
        assert created.event_types == []
        assert created.condition_expression is None
        assert created.enabled is True
        assert created.organization_id == organization_id

    async def test_creates_with_custom_fields(
        self, subscription_service: SubscriptionService, organization_id: uuid.UUID, make_endpoint
    ) -> None:
        endpoint = await make_endpoint()
        created = await subscription_service.create(
            organization_id,
            endpoint_id=endpoint.id,
            scope=SubscriptionScope.PROJECT,
            scope_reference="project-123",
            event_types=["order.created", "order.updated"],
            condition_expression="severity == 'critical'",
        )
        assert created.scope == SubscriptionScope.PROJECT
        assert created.scope_reference == "project-123"
        assert created.event_types == ["order.created", "order.updated"]
        assert created.condition_expression == "severity == 'critical'"


class TestGet:
    async def test_returns_the_matching_subscription(
        self,
        subscription_service: SubscriptionService,
        organization_id: uuid.UUID,
        make_endpoint,
        make_subscription,
    ) -> None:
        endpoint = await make_endpoint()
        created = await make_subscription(endpoint.id)
        found = await subscription_service.get(organization_id, created.id)
        assert found.id == created.id

    async def test_raises_not_found_for_a_missing_id(
        self, subscription_service: SubscriptionService, organization_id: uuid.UUID
    ) -> None:
        with pytest.raises(NotFoundError):
            await subscription_service.get(organization_id, uuid.uuid4())

    async def test_raises_not_found_for_a_cross_org_id(
        self, subscription_service: SubscriptionService, make_endpoint, make_subscription
    ) -> None:
        endpoint = await make_endpoint()
        created = await make_subscription(endpoint.id)
        with pytest.raises(NotFoundError):
            await subscription_service.get(uuid.uuid4(), created.id)


class TestListSubscriptions:
    async def test_lists_every_subscription_in_the_org(
        self,
        subscription_service: SubscriptionService,
        organization_id: uuid.UUID,
        make_endpoint,
        make_subscription,
    ) -> None:
        endpoint = await make_endpoint()
        created = await make_subscription(endpoint.id)
        found = await subscription_service.list_subscriptions(organization_id)
        ids = {one.id for one in found}
        assert created.id in ids

    async def test_tenant_isolation(
        self, subscription_service: SubscriptionService, make_endpoint, make_subscription
    ) -> None:
        endpoint = await make_endpoint()
        await make_subscription(endpoint.id)
        found = await subscription_service.list_subscriptions(uuid.uuid4())
        assert found == []


class TestUpdate:
    async def test_updates_editable_fields(
        self,
        subscription_service: SubscriptionService,
        organization_id: uuid.UUID,
        make_endpoint,
        make_subscription,
    ) -> None:
        endpoint = await make_endpoint()
        created = await make_subscription(endpoint.id)
        updated = await subscription_service.update(
            organization_id,
            created.id,
            scope_reference="new-reference",
            event_types=["order.created"],
            condition_expression="status == 'open'",
            enabled=False,
        )
        assert updated.scope_reference == "new-reference"
        assert updated.event_types == ["order.created"]
        assert updated.condition_expression == "status == 'open'"
        assert updated.enabled is False

    async def test_ignores_a_non_editable_field(
        self,
        subscription_service: SubscriptionService,
        organization_id: uuid.UUID,
        make_endpoint,
        make_subscription,
    ) -> None:
        endpoint = await make_endpoint()
        created = await make_subscription(endpoint.id, scope=SubscriptionScope.WILDCARD)
        updated = await subscription_service.update(
            organization_id, created.id, scope=SubscriptionScope.PROJECT
        )
        assert updated.scope == SubscriptionScope.WILDCARD

    async def test_ignores_none_values(
        self,
        subscription_service: SubscriptionService,
        organization_id: uuid.UUID,
        make_endpoint,
        make_subscription,
    ) -> None:
        endpoint = await make_endpoint()
        created = await make_subscription(endpoint.id, scope_reference="keep-me")
        updated = await subscription_service.update(
            organization_id, created.id, scope_reference=None, condition_expression="x == 1"
        )
        assert updated.scope_reference == "keep-me"
        assert updated.condition_expression == "x == 1"

    async def test_raises_not_found_for_a_missing_id(
        self, subscription_service: SubscriptionService, organization_id: uuid.UUID
    ) -> None:
        with pytest.raises(NotFoundError):
            await subscription_service.update(organization_id, uuid.uuid4(), enabled=False)

    async def test_raises_not_found_for_a_cross_org_id(
        self, subscription_service: SubscriptionService, make_endpoint, make_subscription
    ) -> None:
        endpoint = await make_endpoint()
        created = await make_subscription(endpoint.id)
        with pytest.raises(NotFoundError):
            await subscription_service.update(uuid.uuid4(), created.id, enabled=False)


class TestDelete:
    async def test_deletes_the_subscription(
        self,
        subscription_service: SubscriptionService,
        organization_id: uuid.UUID,
        make_endpoint,
        make_subscription,
    ) -> None:
        endpoint = await make_endpoint()
        created = await make_subscription(endpoint.id)
        await subscription_service.delete(organization_id, created.id)
        with pytest.raises(NotFoundError):
            await subscription_service.get(organization_id, created.id)

    async def test_raises_not_found_for_a_missing_id(
        self, subscription_service: SubscriptionService, organization_id: uuid.UUID
    ) -> None:
        with pytest.raises(NotFoundError):
            await subscription_service.delete(organization_id, uuid.uuid4())

    async def test_raises_not_found_for_a_cross_org_id(
        self, subscription_service: SubscriptionService, make_endpoint, make_subscription
    ) -> None:
        endpoint = await make_endpoint()
        created = await make_subscription(endpoint.id)
        with pytest.raises(NotFoundError):
            await subscription_service.delete(uuid.uuid4(), created.id)


class TestResolveMatching:
    async def test_a_wildcard_subscription_matches_any_event(
        self,
        subscription_service: SubscriptionService,
        organization_id: uuid.UUID,
        make_endpoint,
        make_subscription,
    ) -> None:
        endpoint = await make_endpoint()
        created = await make_subscription(endpoint.id, scope=SubscriptionScope.WILDCARD)
        event = EventContext(event_type="order.created", organization_id=str(organization_id))
        matched = await subscription_service.resolve_matching(organization_id, event)
        assert [one.id for one in matched] == [created.id]

    async def test_an_event_scoped_subscription_matches_by_glob_pattern(
        self,
        subscription_service: SubscriptionService,
        organization_id: uuid.UUID,
        make_endpoint,
        make_subscription,
    ) -> None:
        endpoint = await make_endpoint()
        created = await make_subscription(
            endpoint.id, scope=SubscriptionScope.EVENT, scope_reference="order.*"
        )
        event = EventContext(event_type="order.created", organization_id=str(organization_id))
        matched = await subscription_service.resolve_matching(organization_id, event)
        assert [one.id for one in matched] == [created.id]

        non_matching_event = EventContext(
            event_type="invoice.created", organization_id=str(organization_id)
        )
        assert (
            await subscription_service.resolve_matching(organization_id, non_matching_event) == []
        )

    async def test_event_types_narrows_a_wildcard_subscription(
        self,
        subscription_service: SubscriptionService,
        organization_id: uuid.UUID,
        make_endpoint,
        make_subscription,
    ) -> None:
        endpoint = await make_endpoint()
        created = await make_subscription(
            endpoint.id, scope=SubscriptionScope.WILDCARD, event_types=["order.created"]
        )
        matching_event = EventContext(
            event_type="order.created", organization_id=str(organization_id)
        )
        assert [
            one.id
            for one in await subscription_service.resolve_matching(organization_id, matching_event)
        ] == [created.id]

        other_event = EventContext(
            event_type="invoice.created", organization_id=str(organization_id)
        )
        assert await subscription_service.resolve_matching(organization_id, other_event) == []

    async def test_a_disabled_subscription_never_matches(
        self,
        subscription_service: SubscriptionService,
        organization_id: uuid.UUID,
        make_endpoint,
        make_subscription,
    ) -> None:
        endpoint = await make_endpoint()
        created = await make_subscription(endpoint.id, scope=SubscriptionScope.WILDCARD)
        await subscription_service.update(organization_id, created.id, enabled=False)
        event = EventContext(event_type="order.created", organization_id=str(organization_id))
        assert await subscription_service.resolve_matching(organization_id, event) == []

    async def test_tenant_isolation(
        self,
        subscription_service: SubscriptionService,
        organization_id: uuid.UUID,
        make_endpoint,
        make_subscription,
    ) -> None:
        endpoint = await make_endpoint()
        await make_subscription(endpoint.id, scope=SubscriptionScope.WILDCARD)
        event = EventContext(event_type="order.created", organization_id=str(organization_id))
        matched = await subscription_service.resolve_matching(uuid.uuid4(), event)
        assert matched == []

    async def test_returns_the_actual_subscription_rows_not_just_ids(
        self,
        subscription_service: SubscriptionService,
        organization_id: uuid.UUID,
        make_endpoint,
        make_subscription,
    ) -> None:
        endpoint = await make_endpoint()
        created = await make_subscription(endpoint.id, scope=SubscriptionScope.WILDCARD)
        event = EventContext(event_type="order.created", organization_id=str(organization_id))
        [matched] = await subscription_service.resolve_matching(organization_id, event)
        assert matched.id == created.id
        assert matched.endpoint_id == endpoint.id
        assert matched.scope == SubscriptionScope.WILDCARD


class TestWebhookSubscriptionRepository:
    """Direct repository-level coverage for paths no service method reaches."""

    async def test_require_in_org_raises_not_found_for_other_org(
        self, subscriptions_repo: WebhookSubscriptionRepository, make_endpoint, make_subscription
    ) -> None:
        endpoint = await make_endpoint()
        created = await make_subscription(endpoint.id)
        with pytest.raises(NotFoundError):
            await subscriptions_repo.require_in_org(uuid.uuid4(), created.id)

    async def test_list_enabled_for_org_excludes_disabled(
        self,
        subscriptions_repo: WebhookSubscriptionRepository,
        subscription_service: SubscriptionService,
        organization_id: uuid.UUID,
        make_endpoint,
        make_subscription,
    ) -> None:
        endpoint = await make_endpoint()
        enabled = await make_subscription(endpoint.id)
        disabled = await make_subscription(endpoint.id)
        await subscription_service.update(organization_id, disabled.id, enabled=False)

        found = await subscriptions_repo.list_enabled_for_org(organization_id)
        ids = {one.id for one in found}
        assert enabled.id in ids
        assert disabled.id not in ids

    async def test_list_for_endpoint_scopes_by_endpoint(
        self,
        subscriptions_repo: WebhookSubscriptionRepository,
        organization_id: uuid.UUID,
        make_endpoint,
        make_subscription,
    ) -> None:
        endpoint_a = await make_endpoint(name="endpoint-a")
        endpoint_b = await make_endpoint(name="endpoint-b")
        sub_a = await make_subscription(endpoint_a.id)
        await make_subscription(endpoint_b.id)

        found = await subscriptions_repo.list_for_endpoint(organization_id, endpoint_a.id)
        assert [one.id for one in found] == [sub_a.id]
