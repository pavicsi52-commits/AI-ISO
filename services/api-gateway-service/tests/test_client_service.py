"""ClientService and ApiClientRepository: registration and editing.

Against real PostgreSQL, in a SAVEPOINT-isolated session per test.
"""

from __future__ import annotations

import uuid

import pytest
from shared_core.exceptions.not_found import NotFoundError

from app.models.enums import ClientKind, QuotaKind, QuotaScope, RateLimitScope
from app.repositories.client import ApiClientRepository
from app.services.client import ClientService


class TestRegister:
    async def test_creates_with_defaults(
        self, client_service: ClientService, organization_id: uuid.UUID
    ) -> None:
        created = await client_service.register(organization_id, name="mobile-app")
        assert created.name == "mobile-app"
        assert created.client_kind == ClientKind.THIRD_PARTY
        assert created.description is None
        assert created.contact_email is None
        assert created.enabled is True
        assert created.organization_id == organization_id

    async def test_creates_with_custom_fields(
        self, client_service: ClientService, organization_id: uuid.UUID
    ) -> None:
        created = await client_service.register(
            organization_id,
            name="agent-x",
            client_kind=ClientKind.AI_AGENT,
            description="An AI agent client",
            contact_email="agent@example.com",
        )
        assert created.client_kind == ClientKind.AI_AGENT
        assert created.description == "An AI agent client"
        assert created.contact_email == "agent@example.com"

    async def test_sets_created_by_from_actor_id(
        self, client_service: ClientService, organization_id: uuid.UUID
    ) -> None:
        actor_id = uuid.uuid4()
        created = await client_service.register(
            organization_id, name="mobile-app", actor_id=str(actor_id)
        )
        assert created.created_by == actor_id

    async def test_created_by_is_none_without_actor_id(
        self, client_service: ClientService, organization_id: uuid.UUID
    ) -> None:
        created = await client_service.register(organization_id, name="mobile-app")
        assert created.created_by is None


class TestGet:
    async def test_returns_the_matching_client(
        self, client_service: ClientService, organization_id: uuid.UUID, make_client
    ) -> None:
        created = await make_client()
        found = await client_service.get(organization_id, created.id)
        assert found.id == created.id

    async def test_raises_not_found_for_a_missing_id(
        self, client_service: ClientService, organization_id: uuid.UUID
    ) -> None:
        with pytest.raises(NotFoundError):
            await client_service.get(organization_id, uuid.uuid4())

    async def test_raises_not_found_for_a_cross_org_id(
        self, client_service: ClientService, make_client
    ) -> None:
        created = await make_client()
        with pytest.raises(NotFoundError):
            await client_service.get(uuid.uuid4(), created.id)


class TestListClients:
    async def test_lists_every_client_in_the_org(
        self, client_service: ClientService, organization_id: uuid.UUID, make_client
    ) -> None:
        created = await make_client(name="client-a")
        found = await client_service.list_clients(organization_id)
        ids = {one.id for one in found}
        assert created.id in ids

    async def test_tenant_isolation(self, client_service: ClientService, make_client) -> None:
        await make_client(name="client-a")
        found = await client_service.list_clients(uuid.uuid4())
        assert found == []


class TestUpdate:
    async def test_updates_editable_fields(
        self,
        client_service: ClientService,
        organization_id: uuid.UUID,
        make_client,
        make_rate_limit_policy,
        make_quota_policy,
    ) -> None:
        created = await make_client()
        rate_limit_policy = await make_rate_limit_policy(scope=RateLimitScope.ORGANIZATION)
        quota_policy = await make_quota_policy(scope=QuotaScope.CLIENT, kind=QuotaKind.REQUEST)
        updated = await client_service.update(
            organization_id,
            created.id,
            description="Updated description",
            contact_email="new@example.com",
            default_rate_limit_id=rate_limit_policy.id,
            default_quota_id=quota_policy.id,
            enabled=False,
        )
        assert updated.description == "Updated description"
        assert updated.contact_email == "new@example.com"
        assert updated.default_rate_limit_id == rate_limit_policy.id
        assert updated.default_quota_id == quota_policy.id
        assert updated.enabled is False

    async def test_ignores_a_non_editable_field(
        self, client_service: ClientService, organization_id: uuid.UUID, make_client
    ) -> None:
        created = await make_client(name="original-name", client_kind=ClientKind.THIRD_PARTY)
        updated = await client_service.update(
            organization_id, created.id, name="renamed", client_kind=ClientKind.SDK
        )
        assert updated.name == "original-name"
        assert updated.client_kind == ClientKind.THIRD_PARTY

    async def test_ignores_none_values(
        self, client_service: ClientService, organization_id: uuid.UUID, make_client
    ) -> None:
        created = await make_client(description="Keep me")
        updated = await client_service.update(
            organization_id, created.id, description=None, contact_email="kept@example.com"
        )
        assert updated.description == "Keep me"
        assert updated.contact_email == "kept@example.com"

    async def test_sets_updated_by_from_actor_id(
        self, client_service: ClientService, organization_id: uuid.UUID, make_client
    ) -> None:
        created = await make_client()
        actor_id = uuid.uuid4()
        updated = await client_service.update(
            organization_id, created.id, actor_id=str(actor_id), enabled=False
        )
        assert updated.updated_by == actor_id

    async def test_raises_not_found_for_a_missing_id(
        self, client_service: ClientService, organization_id: uuid.UUID
    ) -> None:
        with pytest.raises(NotFoundError):
            await client_service.update(organization_id, uuid.uuid4(), enabled=False)

    async def test_raises_not_found_for_a_cross_org_id(
        self, client_service: ClientService, make_client
    ) -> None:
        created = await make_client()
        with pytest.raises(NotFoundError):
            await client_service.update(uuid.uuid4(), created.id, enabled=False)


class TestApiClientRepository:
    """Direct repository-level coverage for paths no service method reaches."""

    async def test_require_in_org_raises_not_found_for_other_org(
        self, clients_repo: ApiClientRepository, make_client
    ) -> None:
        created = await make_client()
        with pytest.raises(NotFoundError):
            await clients_repo.require_in_org(uuid.uuid4(), created.id)

    async def test_list_for_org_is_scoped(
        self, clients_repo: ApiClientRepository, organization_id: uuid.UUID, make_client
    ) -> None:
        created = await make_client()
        found = await clients_repo.list_for_org(organization_id)
        ids = {one.id for one in found}
        assert created.id in ids

        found_other_org = await clients_repo.list_for_org(uuid.uuid4())
        assert found_other_org == []
