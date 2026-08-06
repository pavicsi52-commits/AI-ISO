"""EndpointService and WebhookEndpointRepository: registration, editing, health tracking.

Against real PostgreSQL, in a SAVEPOINT-isolated session per test.
"""

from __future__ import annotations

import uuid

import pytest
from shared_core.exceptions.not_found import NotFoundError
from shared_core.exceptions.validation import ValidationError

from app.models.enums import EndpointStatus, WebhookAuthMethod, WebhookKind
from app.repositories.endpoint import WebhookEndpointRepository
from app.services.endpoint import EndpointService
from tests.conftest import FAKE_BACKEND_URL


class TestRegister:
    async def test_creates_with_defaults(
        self, endpoint_service: EndpointService, organization_id: uuid.UUID
    ) -> None:
        created = await endpoint_service.register(
            organization_id, name="orders-endpoint", url=f"{FAKE_BACKEND_URL}/echo"
        )
        assert created.name == "orders-endpoint"
        assert created.description is None
        assert created.url == f"{FAKE_BACKEND_URL}/echo"
        assert created.kind == WebhookKind.OUTGOING
        assert created.auth_method == WebhookAuthMethod.HMAC_SHA256
        assert created.headers == {}
        assert created.status == EndpointStatus.ACTIVE
        assert created.owner_id is None
        assert created.timeout_seconds is None
        assert created.max_attempts is None
        assert created.consecutive_failures == 0
        assert created.enabled is True
        assert created.organization_id == organization_id
        assert created.created_by is None

    async def test_creates_with_custom_fields(
        self, endpoint_service: EndpointService, organization_id: uuid.UUID
    ) -> None:
        created = await endpoint_service.register(
            organization_id,
            name="partner-endpoint",
            url=f"{FAKE_BACKEND_URL}/echo",
            kind=WebhookKind.PARTNER,
            auth_method=WebhookAuthMethod.API_KEY,
            description="A partner delivery target",
            headers={"X-Partner": "acme"},
            owner_id="team-payments",
            timeout_seconds=12.5,
            max_attempts=5,
        )
        assert created.kind == WebhookKind.PARTNER
        assert created.auth_method == WebhookAuthMethod.API_KEY
        assert created.description == "A partner delivery target"
        assert created.headers == {"X-Partner": "acme"}
        assert created.owner_id == "team-payments"
        assert created.timeout_seconds == 12.5
        assert created.max_attempts == 5

    async def test_sets_created_by_from_actor_id(
        self, endpoint_service: EndpointService, organization_id: uuid.UUID
    ) -> None:
        actor_id = uuid.uuid4()
        created = await endpoint_service.register(
            organization_id,
            name="orders-endpoint",
            url=f"{FAKE_BACKEND_URL}/echo",
            actor_id=str(actor_id),
        )
        assert created.created_by == actor_id

    async def test_rejects_a_non_http_scheme(
        self, endpoint_service: EndpointService, organization_id: uuid.UUID
    ) -> None:
        with pytest.raises(ValidationError):
            await endpoint_service.register(organization_id, name="ftp-endpoint", url="ftp://example.com/x")

    async def test_rejects_an_unresolvable_host(
        self, endpoint_service: EndpointService, organization_id: uuid.UUID
    ) -> None:
        with pytest.raises(ValidationError):
            await endpoint_service.register(
                organization_id,
                name="bad-host",
                url="http://this-host-does-not-exist.invalid/x",
            )

    async def test_rejects_a_private_address(
        self, endpoint_service: EndpointService, organization_id: uuid.UUID
    ) -> None:
        with pytest.raises(ValidationError):
            await endpoint_service.register(organization_id, name="private", url="http://10.0.0.5/x")

    async def test_rejects_a_link_local_address(
        self, endpoint_service: EndpointService, organization_id: uuid.UUID
    ) -> None:
        with pytest.raises(ValidationError):
            await endpoint_service.register(
                organization_id, name="metadata", url="http://169.254.169.254/latest/meta-data"
            )


class TestGet:
    async def test_returns_the_matching_endpoint(
        self, endpoint_service: EndpointService, organization_id: uuid.UUID, make_endpoint
    ) -> None:
        created = await make_endpoint()
        found = await endpoint_service.get(organization_id, created.id)
        assert found.id == created.id

    async def test_raises_not_found_for_a_missing_id(
        self, endpoint_service: EndpointService, organization_id: uuid.UUID
    ) -> None:
        with pytest.raises(NotFoundError):
            await endpoint_service.get(organization_id, uuid.uuid4())

    async def test_raises_not_found_for_a_cross_org_id(
        self, endpoint_service: EndpointService, make_endpoint
    ) -> None:
        created = await make_endpoint()
        with pytest.raises(NotFoundError):
            await endpoint_service.get(uuid.uuid4(), created.id)


class TestListEndpoints:
    async def test_lists_every_endpoint_in_the_org(
        self, endpoint_service: EndpointService, organization_id: uuid.UUID, make_endpoint
    ) -> None:
        created = await make_endpoint(name="orders")
        found = await endpoint_service.list_endpoints(organization_id)
        ids = {one.id for one in found}
        assert created.id in ids

    async def test_filters_by_enabled_true(
        self, endpoint_service: EndpointService, organization_id: uuid.UUID, make_endpoint
    ) -> None:
        enabled = await make_endpoint(name="enabled-endpoint")
        disabled = await make_endpoint(name="disabled-endpoint")
        await endpoint_service.update(organization_id, disabled.id, enabled=False)

        only_enabled = await endpoint_service.list_endpoints(organization_id, enabled=True)
        ids = {one.id for one in only_enabled}
        assert enabled.id in ids
        assert disabled.id not in ids

    async def test_filters_by_enabled_false(
        self, endpoint_service: EndpointService, organization_id: uuid.UUID, make_endpoint
    ) -> None:
        enabled = await make_endpoint(name="enabled-endpoint")
        disabled = await make_endpoint(name="disabled-endpoint")
        await endpoint_service.update(organization_id, disabled.id, enabled=False)

        only_disabled = await endpoint_service.list_endpoints(organization_id, enabled=False)
        ids = {one.id for one in only_disabled}
        assert disabled.id in ids
        assert enabled.id not in ids

    async def test_tenant_isolation(self, endpoint_service: EndpointService, make_endpoint) -> None:
        await make_endpoint(name="orders")
        found = await endpoint_service.list_endpoints(uuid.uuid4())
        assert found == []


class TestUpdate:
    async def test_updates_editable_fields(
        self, endpoint_service: EndpointService, organization_id: uuid.UUID, make_endpoint
    ) -> None:
        created = await make_endpoint()
        updated = await endpoint_service.update(
            organization_id,
            created.id,
            name="renamed",
            description="new description",
            url=f"{FAKE_BACKEND_URL}/echo",
            auth_method=WebhookAuthMethod.NONE,
            headers={"X-New": "1"},
            status=EndpointStatus.DISABLED,
            owner_id="team-x",
            timeout_seconds=3.5,
            max_attempts=2,
            backoff_strategy="linear",
            enabled=False,
        )
        assert updated.name == "renamed"
        assert updated.description == "new description"
        assert updated.auth_method == WebhookAuthMethod.NONE
        assert updated.headers == {"X-New": "1"}
        assert updated.status == EndpointStatus.DISABLED
        assert updated.owner_id == "team-x"
        assert updated.timeout_seconds == 3.5
        assert updated.max_attempts == 2
        assert updated.backoff_strategy == "linear"
        assert updated.enabled is False

    async def test_ignores_a_non_editable_field(
        self, endpoint_service: EndpointService, organization_id: uuid.UUID, make_endpoint
    ) -> None:
        created = await make_endpoint(name="orders")
        updated = await endpoint_service.update(organization_id, created.id, kind=WebhookKind.INCOMING)
        assert updated.kind == WebhookKind.OUTGOING

    async def test_ignores_none_values(
        self, endpoint_service: EndpointService, organization_id: uuid.UUID, make_endpoint
    ) -> None:
        created = await make_endpoint(description="keep me")
        updated = await endpoint_service.update(
            organization_id, created.id, description=None, owner_id="team-y"
        )
        assert updated.description == "keep me"
        assert updated.owner_id == "team-y"

    async def test_revalidates_a_changed_url(
        self, endpoint_service: EndpointService, organization_id: uuid.UUID, make_endpoint
    ) -> None:
        created = await make_endpoint()
        with pytest.raises(ValidationError):
            await endpoint_service.update(organization_id, created.id, url="http://10.0.0.5/x")

    async def test_sets_updated_by_from_actor_id(
        self, endpoint_service: EndpointService, organization_id: uuid.UUID, make_endpoint
    ) -> None:
        created = await make_endpoint()
        actor_id = uuid.uuid4()
        updated = await endpoint_service.update(
            organization_id, created.id, actor_id=str(actor_id), enabled=False
        )
        assert updated.updated_by == actor_id

    async def test_updated_by_is_none_without_actor_id(
        self, endpoint_service: EndpointService, organization_id: uuid.UUID, make_endpoint
    ) -> None:
        created = await make_endpoint()
        updated = await endpoint_service.update(organization_id, created.id, enabled=False)
        assert updated.updated_by is None

    async def test_raises_not_found_for_a_missing_id(
        self, endpoint_service: EndpointService, organization_id: uuid.UUID
    ) -> None:
        with pytest.raises(NotFoundError):
            await endpoint_service.update(organization_id, uuid.uuid4(), enabled=False)

    async def test_raises_not_found_for_a_cross_org_id(
        self, endpoint_service: EndpointService, make_endpoint
    ) -> None:
        created = await make_endpoint()
        with pytest.raises(NotFoundError):
            await endpoint_service.update(uuid.uuid4(), created.id, enabled=False)


class TestDelete:
    async def test_deletes_the_endpoint(
        self, endpoint_service: EndpointService, organization_id: uuid.UUID, make_endpoint
    ) -> None:
        created = await make_endpoint()
        await endpoint_service.delete(organization_id, created.id)
        with pytest.raises(NotFoundError):
            await endpoint_service.get(organization_id, created.id)

    async def test_sets_deleted_by_from_actor_id(
        self,
        endpoint_service: EndpointService,
        endpoints_repo: WebhookEndpointRepository,
        organization_id: uuid.UUID,
        make_endpoint,
    ) -> None:
        created = await make_endpoint()
        actor_id = uuid.uuid4()
        await endpoint_service.delete(organization_id, created.id, actor_id=str(actor_id))
        raw = await endpoints_repo.get_by_id(created.id, include_deleted=True)
        assert raw is not None
        assert raw.deleted_by == actor_id
        assert raw.is_active is False

    async def test_raises_not_found_for_a_missing_id(
        self, endpoint_service: EndpointService, organization_id: uuid.UUID
    ) -> None:
        with pytest.raises(NotFoundError):
            await endpoint_service.delete(organization_id, uuid.uuid4())

    async def test_raises_not_found_for_a_cross_org_id(
        self, endpoint_service: EndpointService, make_endpoint
    ) -> None:
        created = await make_endpoint()
        with pytest.raises(NotFoundError):
            await endpoint_service.delete(uuid.uuid4(), created.id)


class TestRecordDeliveryOutcome:
    async def test_success_resets_consecutive_failures_and_sets_last_delivered_at(
        self, endpoint_service: EndpointService, organization_id: uuid.UUID, make_endpoint
    ) -> None:
        created = await make_endpoint()
        await endpoint_service.record_delivery_outcome(organization_id, created.id, succeeded=False)
        await endpoint_service.record_delivery_outcome(organization_id, created.id, succeeded=False)
        found = await endpoint_service.get(organization_id, created.id)
        assert found.consecutive_failures == 2

        await endpoint_service.record_delivery_outcome(organization_id, created.id, succeeded=True)
        found = await endpoint_service.get(organization_id, created.id)
        assert found.consecutive_failures == 0
        assert found.last_delivered_at is not None

    async def test_success_recovers_an_unhealthy_endpoint_to_active(
        self, endpoint_service: EndpointService, organization_id: uuid.UUID, make_endpoint
    ) -> None:
        created = await make_endpoint()
        await endpoint_service.update(organization_id, created.id, status=EndpointStatus.UNHEALTHY)
        await endpoint_service.record_delivery_outcome(organization_id, created.id, succeeded=True)
        found = await endpoint_service.get(organization_id, created.id)
        assert found.status == EndpointStatus.ACTIVE

    async def test_success_leaves_a_disabled_status_untouched(
        self, endpoint_service: EndpointService, organization_id: uuid.UUID, make_endpoint
    ) -> None:
        created = await make_endpoint()
        await endpoint_service.update(organization_id, created.id, status=EndpointStatus.DISABLED)
        await endpoint_service.record_delivery_outcome(organization_id, created.id, succeeded=True)
        found = await endpoint_service.get(organization_id, created.id)
        assert found.status == EndpointStatus.DISABLED

    async def test_failure_increments_consecutive_failures_and_sets_last_failed_at(
        self, endpoint_service: EndpointService, organization_id: uuid.UUID, make_endpoint
    ) -> None:
        created = await make_endpoint()
        await endpoint_service.record_delivery_outcome(organization_id, created.id, succeeded=False)
        found = await endpoint_service.get(organization_id, created.id)
        assert found.consecutive_failures == 1
        assert found.last_failed_at is not None

    async def test_raises_not_found_for_a_missing_id(
        self, endpoint_service: EndpointService, organization_id: uuid.UUID
    ) -> None:
        with pytest.raises(NotFoundError):
            await endpoint_service.record_delivery_outcome(organization_id, uuid.uuid4(), succeeded=True)


class TestWebhookEndpointRepository:
    """Direct repository-level coverage for paths no service method reaches."""

    async def test_require_in_org_raises_not_found_for_other_org(
        self, endpoints_repo: WebhookEndpointRepository, make_endpoint
    ) -> None:
        created = await make_endpoint()
        with pytest.raises(NotFoundError):
            await endpoints_repo.require_in_org(uuid.uuid4(), created.id)

    async def test_list_all_enabled_is_unscoped_by_organization(
        self, endpoints_repo: WebhookEndpointRepository, make_endpoint
    ) -> None:
        other_org_endpoint = await make_endpoint(name="other-org-endpoint")
        all_enabled = await endpoints_repo.list_all_enabled()
        ids = {one.id for one in all_enabled}
        assert other_org_endpoint.id in ids

    async def test_list_all_enabled_excludes_disabled(
        self,
        endpoints_repo: WebhookEndpointRepository,
        endpoint_service: EndpointService,
        organization_id: uuid.UUID,
        make_endpoint,
    ) -> None:
        disabled = await make_endpoint(name="disabled-endpoint")
        await endpoint_service.update(organization_id, disabled.id, enabled=False)
        all_enabled = await endpoints_repo.list_all_enabled()
        ids = {one.id for one in all_enabled}
        assert disabled.id not in ids

    async def test_list_all_enabled_respects_limit(
        self, endpoints_repo: WebhookEndpointRepository, make_endpoint
    ) -> None:
        await make_endpoint(name="endpoint-a")
        await make_endpoint(name="endpoint-b")
        limited = await endpoints_repo.list_all_enabled(limit=1)
        assert len(limited) == 1
