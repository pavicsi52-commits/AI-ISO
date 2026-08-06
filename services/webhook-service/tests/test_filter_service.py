"""FilterService and WebhookFilterRepository: rule-set registration and pass evaluation.

Against real PostgreSQL, in a SAVEPOINT-isolated session per test.

``passes`` is the integration point between this service and the pure
``app.filters.engine`` module (its own dedicated, exhaustively-tested pure
module): these tests prove the service correctly assembles a subscription's
own enabled rule sets from real persisted rows and gates on them -- not the
rule-evaluation algorithm's own behaviour in depth.
"""

from __future__ import annotations

import uuid

import pytest
from shared_core.exceptions.not_found import NotFoundError

from app.models.enums import FilterMatchMode
from app.models.filter import WebhookFilter
from app.repositories.filter import WebhookFilterRepository
from app.services.filter import FilterService


class TestCreate:
    async def test_creates_with_defaults(
        self,
        filter_service: FilterService,
        organization_id: uuid.UUID,
        make_endpoint,
        make_subscription,
    ) -> None:
        endpoint = await make_endpoint()
        subscription = await make_subscription(endpoint.id)
        created = await filter_service.create(
            organization_id, subscription_id=subscription.id, name="severity-filter", rules=[]
        )
        assert created.subscription_id == subscription.id
        assert created.name == "severity-filter"
        assert created.match_mode == FilterMatchMode.ALL
        assert created.rules == []
        assert created.enabled is True
        assert created.organization_id == organization_id

    async def test_creates_with_custom_fields(
        self,
        filter_service: FilterService,
        organization_id: uuid.UUID,
        make_endpoint,
        make_subscription,
    ) -> None:
        endpoint = await make_endpoint()
        subscription = await make_subscription(endpoint.id)
        rules = [{"field": "severity", "operator": "eq", "value": "critical"}]
        created = await filter_service.create(
            organization_id,
            subscription_id=subscription.id,
            name="critical-only",
            rules=rules,
            match_mode=FilterMatchMode.ANY,
        )
        assert created.match_mode == FilterMatchMode.ANY
        assert created.rules == rules


class TestGet:
    async def test_returns_the_matching_filter(
        self,
        filter_service: FilterService,
        organization_id: uuid.UUID,
        make_endpoint,
        make_subscription,
    ) -> None:
        endpoint = await make_endpoint()
        subscription = await make_subscription(endpoint.id)
        created = await filter_service.create(
            organization_id, subscription_id=subscription.id, name="f", rules=[]
        )
        found = await filter_service.get(organization_id, created.id)
        assert found.id == created.id

    async def test_raises_not_found_for_a_missing_id(
        self, filter_service: FilterService, organization_id: uuid.UUID
    ) -> None:
        with pytest.raises(NotFoundError):
            await filter_service.get(organization_id, uuid.uuid4())

    async def test_raises_not_found_for_a_cross_org_id(
        self,
        filter_service: FilterService,
        organization_id: uuid.UUID,
        make_endpoint,
        make_subscription,
    ) -> None:
        endpoint = await make_endpoint()
        subscription = await make_subscription(endpoint.id)
        created = await filter_service.create(
            organization_id, subscription_id=subscription.id, name="f", rules=[]
        )
        with pytest.raises(NotFoundError):
            await filter_service.get(uuid.uuid4(), created.id)


class TestListForSubscription:
    async def test_lists_every_enabled_filter(
        self,
        filter_service: FilterService,
        organization_id: uuid.UUID,
        make_endpoint,
        make_subscription,
    ) -> None:
        endpoint = await make_endpoint()
        subscription = await make_subscription(endpoint.id)
        created = await filter_service.create(
            organization_id, subscription_id=subscription.id, name="f", rules=[]
        )
        found = await filter_service.list_for_subscription(subscription.id)
        assert [one.id for one in found] == [created.id]

    async def test_excludes_disabled_filters(
        self,
        filter_service: FilterService,
        filters_repo: WebhookFilterRepository,
        organization_id: uuid.UUID,
        make_endpoint,
        make_subscription,
    ) -> None:
        endpoint = await make_endpoint()
        subscription = await make_subscription(endpoint.id)
        await filters_repo.create(
            WebhookFilter(
                organization_id=organization_id,
                subscription_id=subscription.id,
                name="disabled-filter",
                rules=[],
                enabled=False,
            )
        )
        found = await filter_service.list_for_subscription(subscription.id)
        assert found == []

    async def test_scoped_by_subscription(
        self,
        filter_service: FilterService,
        organization_id: uuid.UUID,
        make_endpoint,
        make_subscription,
    ) -> None:
        endpoint = await make_endpoint()
        subscription_a = await make_subscription(endpoint.id)
        subscription_b = await make_subscription(endpoint.id)
        created_a = await filter_service.create(
            organization_id, subscription_id=subscription_a.id, name="f-a", rules=[]
        )
        await filter_service.create(
            organization_id, subscription_id=subscription_b.id, name="f-b", rules=[]
        )

        found = await filter_service.list_for_subscription(subscription_a.id)
        assert [one.id for one in found] == [created_a.id]


class TestPasses:
    async def test_a_subscription_with_no_filters_always_passes(
        self, filter_service: FilterService, make_endpoint, make_subscription
    ) -> None:
        endpoint = await make_endpoint()
        subscription = await make_subscription(endpoint.id)
        assert await filter_service.passes(subscription.id, {"severity": "info"}) is True

    async def test_all_mode_requires_every_rule_to_match(
        self,
        filter_service: FilterService,
        organization_id: uuid.UUID,
        make_endpoint,
        make_subscription,
    ) -> None:
        endpoint = await make_endpoint()
        subscription = await make_subscription(endpoint.id)
        await filter_service.create(
            organization_id,
            subscription_id=subscription.id,
            name="all-filter",
            match_mode=FilterMatchMode.ALL,
            rules=[
                {"field": "severity", "operator": "eq", "value": "critical"},
                {"field": "status", "operator": "eq", "value": "open"},
            ],
        )
        assert (
            await filter_service.passes(subscription.id, {"severity": "critical", "status": "open"})
            is True
        )
        assert (
            await filter_service.passes(
                subscription.id, {"severity": "critical", "status": "closed"}
            )
            is False
        )

    async def test_any_mode_requires_only_one_rule_to_match(
        self,
        filter_service: FilterService,
        organization_id: uuid.UUID,
        make_endpoint,
        make_subscription,
    ) -> None:
        endpoint = await make_endpoint()
        subscription = await make_subscription(endpoint.id)
        await filter_service.create(
            organization_id,
            subscription_id=subscription.id,
            name="any-filter",
            match_mode=FilterMatchMode.ANY,
            rules=[
                {"field": "severity", "operator": "eq", "value": "critical"},
                {"field": "status", "operator": "eq", "value": "open"},
            ],
        )
        assert (
            await filter_service.passes(subscription.id, {"severity": "info", "status": "open"})
            is True
        )
        assert (
            await filter_service.passes(subscription.id, {"severity": "info", "status": "closed"})
            is False
        )

    async def test_multiple_filters_on_one_subscription_all_must_pass(
        self,
        filter_service: FilterService,
        organization_id: uuid.UUID,
        make_endpoint,
        make_subscription,
    ) -> None:
        endpoint = await make_endpoint()
        subscription = await make_subscription(endpoint.id)
        await filter_service.create(
            organization_id,
            subscription_id=subscription.id,
            name="first",
            rules=[{"field": "severity", "operator": "eq", "value": "critical"}],
        )
        await filter_service.create(
            organization_id,
            subscription_id=subscription.id,
            name="second",
            rules=[{"field": "status", "operator": "eq", "value": "open"}],
        )
        assert (
            await filter_service.passes(subscription.id, {"severity": "critical", "status": "open"})
            is True
        )
        assert (
            await filter_service.passes(
                subscription.id, {"severity": "critical", "status": "closed"}
            )
            is False
        )

    async def test_a_disabled_filter_is_not_considered(
        self,
        filter_service: FilterService,
        filters_repo: WebhookFilterRepository,
        organization_id: uuid.UUID,
        make_endpoint,
        make_subscription,
    ) -> None:
        endpoint = await make_endpoint()
        subscription = await make_subscription(endpoint.id)
        await filters_repo.create(
            WebhookFilter(
                organization_id=organization_id,
                subscription_id=subscription.id,
                name="disabled-filter",
                rules=[{"field": "severity", "operator": "eq", "value": "critical"}],
                enabled=False,
            )
        )
        # The only filter attached is disabled, so this behaves like "no filters".
        assert await filter_service.passes(subscription.id, {"severity": "info"}) is True


class TestWebhookFilterRepository:
    """Direct repository-level coverage for paths no service method reaches."""

    async def test_require_in_org_raises_not_found_for_other_org(
        self,
        filters_repo: WebhookFilterRepository,
        filter_service: FilterService,
        organization_id: uuid.UUID,
        make_endpoint,
        make_subscription,
    ) -> None:
        endpoint = await make_endpoint()
        subscription = await make_subscription(endpoint.id)
        created = await filter_service.create(
            organization_id, subscription_id=subscription.id, name="f", rules=[]
        )
        with pytest.raises(NotFoundError):
            await filters_repo.require_in_org(uuid.uuid4(), created.id)
