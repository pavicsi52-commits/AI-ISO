"""ServiceRegistryService and ApiServiceRepository: registration, editing, lookup.

Against real PostgreSQL, in a SAVEPOINT-isolated session per test.
"""

from __future__ import annotations

import uuid

import pytest
from shared_core.exceptions.not_found import NotFoundError

from app.models.enums import LoadBalancingStrategy
from app.repositories.service import ApiServiceRepository
from app.services.service import ServiceRegistryService
from tests.conftest import FAKE_BACKEND_URL


class TestRegister:
    async def test_creates_with_defaults(
        self, service_registry_service: ServiceRegistryService, organization_id: uuid.UUID
    ) -> None:
        created = await service_registry_service.register(
            organization_id, name="orders", instances=[{"url": FAKE_BACKEND_URL, "weight": 100}]
        )
        assert created.name == "orders"
        assert created.description is None
        assert created.instances == [{"url": FAKE_BACKEND_URL, "weight": 100}]
        assert created.load_balancing_strategy == LoadBalancingStrategy.ROUND_ROBIN
        assert created.health_check_path == "/health"
        assert created.timeout_seconds is None
        assert created.circuit_breaker_enabled is True
        assert created.enabled is True
        assert created.organization_id == organization_id

    async def test_creates_with_custom_fields(
        self, service_registry_service: ServiceRegistryService, organization_id: uuid.UUID
    ) -> None:
        created = await service_registry_service.register(
            organization_id,
            name="payments",
            instances=[{"url": FAKE_BACKEND_URL, "weight": 50}],
            description="Payments backend",
            load_balancing_strategy=LoadBalancingStrategy.LEAST_CONNECTIONS,
            health_check_path="/healthz",
            timeout_seconds=2.5,
            circuit_breaker_enabled=False,
        )
        assert created.description == "Payments backend"
        assert created.load_balancing_strategy == LoadBalancingStrategy.LEAST_CONNECTIONS
        assert created.health_check_path == "/healthz"
        assert created.timeout_seconds == 2.5
        assert created.circuit_breaker_enabled is False

    async def test_sets_created_by_from_actor_id(
        self, service_registry_service: ServiceRegistryService, organization_id: uuid.UUID
    ) -> None:
        actor_id = uuid.uuid4()
        created = await service_registry_service.register(
            organization_id,
            name="orders",
            instances=[{"url": FAKE_BACKEND_URL, "weight": 100}],
            actor_id=str(actor_id),
        )
        assert created.created_by == actor_id

    async def test_created_by_is_none_without_actor_id(
        self, service_registry_service: ServiceRegistryService, organization_id: uuid.UUID
    ) -> None:
        created = await service_registry_service.register(
            organization_id, name="orders", instances=[{"url": FAKE_BACKEND_URL, "weight": 100}]
        )
        assert created.created_by is None


class TestGet:
    async def test_returns_the_matching_service(
        self,
        service_registry_service: ServiceRegistryService,
        organization_id: uuid.UUID,
        make_service,
    ) -> None:
        created = await make_service()
        found = await service_registry_service.get(organization_id, created.id)
        assert found.id == created.id

    async def test_raises_not_found_for_a_missing_id(
        self, service_registry_service: ServiceRegistryService, organization_id: uuid.UUID
    ) -> None:
        with pytest.raises(NotFoundError):
            await service_registry_service.get(organization_id, uuid.uuid4())

    async def test_raises_not_found_for_a_cross_org_id(
        self, service_registry_service: ServiceRegistryService, make_service
    ) -> None:
        created = await make_service()
        with pytest.raises(NotFoundError):
            await service_registry_service.get(uuid.uuid4(), created.id)


class TestGetByName:
    async def test_returns_none_when_no_match(
        self, service_registry_service: ServiceRegistryService, organization_id: uuid.UUID
    ) -> None:
        found = await service_registry_service.get_by_name(organization_id, "does-not-exist")
        assert found is None

    async def test_returns_the_matching_service(
        self,
        service_registry_service: ServiceRegistryService,
        organization_id: uuid.UUID,
        make_service,
    ) -> None:
        created = await make_service(name="orders")
        found = await service_registry_service.get_by_name(organization_id, "orders")
        assert found is not None
        assert found.id == created.id

    async def test_is_scoped_by_organization(
        self, service_registry_service: ServiceRegistryService, make_service
    ) -> None:
        await make_service(name="orders")
        found = await service_registry_service.get_by_name(uuid.uuid4(), "orders")
        assert found is None


class TestListServices:
    async def test_lists_every_service_in_the_org(
        self,
        service_registry_service: ServiceRegistryService,
        organization_id: uuid.UUID,
        make_service,
    ) -> None:
        created = await make_service(name="orders")
        found = await service_registry_service.list_services(organization_id)
        ids = {one.id for one in found}
        assert created.id in ids

    async def test_filters_by_enabled_true(
        self,
        service_registry_service: ServiceRegistryService,
        organization_id: uuid.UUID,
        make_service,
    ) -> None:
        enabled = await make_service(name="enabled-svc")
        disabled = await make_service(name="disabled-svc")
        await service_registry_service.update(organization_id, disabled.id, enabled=False)

        only_enabled = await service_registry_service.list_services(organization_id, enabled=True)
        ids = {one.id for one in only_enabled}
        assert enabled.id in ids
        assert disabled.id not in ids

    async def test_filters_by_enabled_false(
        self,
        service_registry_service: ServiceRegistryService,
        organization_id: uuid.UUID,
        make_service,
    ) -> None:
        enabled = await make_service(name="enabled-svc")
        disabled = await make_service(name="disabled-svc")
        await service_registry_service.update(organization_id, disabled.id, enabled=False)

        only_disabled = await service_registry_service.list_services(organization_id, enabled=False)
        ids = {one.id for one in only_disabled}
        assert disabled.id in ids
        assert enabled.id not in ids

    async def test_tenant_isolation(
        self, service_registry_service: ServiceRegistryService, make_service
    ) -> None:
        await make_service(name="orders")
        found = await service_registry_service.list_services(uuid.uuid4())
        assert found == []


class TestUpdate:
    async def test_updates_editable_fields(
        self,
        service_registry_service: ServiceRegistryService,
        organization_id: uuid.UUID,
        make_service,
    ) -> None:
        created = await make_service()
        updated = await service_registry_service.update(
            organization_id,
            created.id,
            description="Updated",
            instances=[{"url": "http://other.test", "weight": 10}],
            load_balancing_strategy=LoadBalancingStrategy.WEIGHTED,
            health_check_path="/ping",
            timeout_seconds=9.5,
            circuit_breaker_enabled=False,
            enabled=False,
        )
        assert updated.description == "Updated"
        assert updated.instances == [{"url": "http://other.test", "weight": 10}]
        assert updated.load_balancing_strategy == LoadBalancingStrategy.WEIGHTED
        assert updated.health_check_path == "/ping"
        assert updated.timeout_seconds == 9.5
        assert updated.circuit_breaker_enabled is False
        assert updated.enabled is False

    async def test_ignores_a_non_editable_field(
        self,
        service_registry_service: ServiceRegistryService,
        organization_id: uuid.UUID,
        make_service,
    ) -> None:
        created = await make_service(name="orders")
        updated = await service_registry_service.update(organization_id, created.id, name="renamed")
        assert updated.name == "orders"

    async def test_ignores_none_values(
        self,
        service_registry_service: ServiceRegistryService,
        organization_id: uuid.UUID,
        make_service,
    ) -> None:
        created = await make_service(description="Keep me")
        updated = await service_registry_service.update(
            organization_id, created.id, description=None, health_check_path="/ping"
        )
        assert updated.description == "Keep me"
        assert updated.health_check_path == "/ping"

    async def test_sets_updated_by_from_actor_id(
        self,
        service_registry_service: ServiceRegistryService,
        organization_id: uuid.UUID,
        make_service,
    ) -> None:
        created = await make_service()
        actor_id = uuid.uuid4()
        updated = await service_registry_service.update(
            organization_id, created.id, actor_id=str(actor_id), enabled=False
        )
        assert updated.updated_by == actor_id

    async def test_raises_not_found_for_a_missing_id(
        self, service_registry_service: ServiceRegistryService, organization_id: uuid.UUID
    ) -> None:
        with pytest.raises(NotFoundError):
            await service_registry_service.update(organization_id, uuid.uuid4(), enabled=False)

    async def test_raises_not_found_for_a_cross_org_id(
        self, service_registry_service: ServiceRegistryService, make_service
    ) -> None:
        created = await make_service()
        with pytest.raises(NotFoundError):
            await service_registry_service.update(uuid.uuid4(), created.id, enabled=False)


class TestDelete:
    async def test_deletes_the_service(
        self,
        service_registry_service: ServiceRegistryService,
        organization_id: uuid.UUID,
        make_service,
    ) -> None:
        created = await make_service()
        await service_registry_service.delete(organization_id, created.id)
        with pytest.raises(NotFoundError):
            await service_registry_service.get(organization_id, created.id)

    async def test_sets_deleted_by_from_actor_id(
        self,
        service_registry_service: ServiceRegistryService,
        services_repo: ApiServiceRepository,
        organization_id: uuid.UUID,
        make_service,
    ) -> None:
        created = await make_service()
        actor_id = uuid.uuid4()
        await service_registry_service.delete(organization_id, created.id, actor_id=str(actor_id))
        raw = await services_repo.get_by_id(created.id, include_deleted=True)
        assert raw is not None
        assert raw.deleted_by == actor_id
        assert raw.is_active is False

    async def test_raises_not_found_for_a_missing_id(
        self, service_registry_service: ServiceRegistryService, organization_id: uuid.UUID
    ) -> None:
        with pytest.raises(NotFoundError):
            await service_registry_service.delete(organization_id, uuid.uuid4())

    async def test_raises_not_found_for_a_cross_org_id(
        self, service_registry_service: ServiceRegistryService, make_service
    ) -> None:
        created = await make_service()
        with pytest.raises(NotFoundError):
            await service_registry_service.delete(uuid.uuid4(), created.id)


class TestApiServiceRepository:
    """Direct repository-level coverage for paths no service method reaches."""

    async def test_require_in_org_raises_not_found_for_other_org(
        self, services_repo: ApiServiceRepository, make_service
    ) -> None:
        created = await make_service()
        with pytest.raises(NotFoundError):
            await services_repo.require_in_org(uuid.uuid4(), created.id)

    async def test_get_by_name_returns_none_when_no_match(
        self, services_repo: ApiServiceRepository, organization_id: uuid.UUID
    ) -> None:
        found = await services_repo.get_by_name(organization_id, "nope")
        assert found is None

    async def test_list_all_is_unscoped_by_organization(
        self, services_repo: ApiServiceRepository, make_service
    ) -> None:
        other_org_service = await make_service(name="other-org-service")
        all_services = await services_repo.list_all()
        ids = {one.id for one in all_services}
        assert other_org_service.id in ids

    async def test_list_all_respects_limit(
        self, services_repo: ApiServiceRepository, make_service
    ) -> None:
        await make_service(name="svc-a")
        await make_service(name="svc-b")
        limited = await services_repo.list_all(limit=1)
        assert len(limited) == 1
