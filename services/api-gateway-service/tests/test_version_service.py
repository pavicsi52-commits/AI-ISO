"""VersionService and ApiVersionRepository: registration, default demotion, deprecation.

Against real PostgreSQL, in a SAVEPOINT-isolated session per test.
"""

from __future__ import annotations

import uuid

import pytest
from shared_core.exceptions.not_found import NotFoundError

from app.repositories.version import ApiVersionRepository
from app.services.version import VersionService
from tests.conftest import soon


class TestRegister:
    async def test_creates_with_defaults(
        self, version_service: VersionService, organization_id: uuid.UUID, make_service
    ) -> None:
        service = await make_service()
        created = await version_service.register(
            organization_id, service_id=service.id, version="v1"
        )
        assert created.version_label == "v1"
        assert created.is_default is False
        assert created.is_deprecated is False
        assert created.service_id == service.id
        assert created.organization_id == organization_id

    async def test_first_default_version_needs_no_demotion(
        self, version_service: VersionService, organization_id: uuid.UUID, make_service
    ) -> None:
        service = await make_service()
        created = await version_service.register(
            organization_id, service_id=service.id, version="v1", is_default=True
        )
        assert created.is_default is True

    async def test_registering_a_new_default_demotes_the_previous_one(
        self, version_service: VersionService, organization_id: uuid.UUID, make_service
    ) -> None:
        service = await make_service()
        v1 = await version_service.register(
            organization_id, service_id=service.id, version="v1", is_default=True
        )
        v2 = await version_service.register(
            organization_id, service_id=service.id, version="v2", is_default=True
        )

        versions = {
            v.version_label: v
            for v in await version_service.list_for_service(organization_id, service.id)
        }
        assert versions["v1"].is_default is False
        assert versions["v2"].is_default is True
        assert v1.id != v2.id

    async def test_demotes_exactly_one_previously_default_version(
        self, version_service: VersionService, organization_id: uuid.UUID, make_service
    ) -> None:
        service = await make_service()
        await version_service.register(
            organization_id, service_id=service.id, version="v1", is_default=True
        )
        await version_service.register(
            organization_id, service_id=service.id, version="v2", is_default=False
        )
        await version_service.register(
            organization_id, service_id=service.id, version="v3", is_default=True
        )

        versions = {
            v.version_label: v
            for v in await version_service.list_for_service(organization_id, service.id)
        }
        assert versions["v1"].is_default is False
        assert versions["v2"].is_default is False
        assert versions["v3"].is_default is True

    async def test_does_not_demote_a_different_services_default(
        self, version_service: VersionService, organization_id: uuid.UUID, make_service
    ) -> None:
        service_a = await make_service(name="service-a")
        service_b = await make_service(name="service-b")
        await version_service.register(
            organization_id, service_id=service_a.id, version="v1", is_default=True
        )
        await version_service.register(
            organization_id, service_id=service_b.id, version="v1", is_default=True
        )

        a_versions = await version_service.list_for_service(organization_id, service_a.id)
        assert a_versions[0].is_default is True

    async def test_does_not_demote_a_different_organizations_default(
        self, version_service: VersionService, organization_id: uuid.UUID, make_service
    ) -> None:
        service = await make_service()
        other_org = uuid.uuid4()
        await version_service.register(
            organization_id, service_id=service.id, version="v1", is_default=True
        )

        # A different organization registering a default version against the
        # same service_id must never see, let alone demote, this org's row.
        await version_service.register(
            other_org, service_id=service.id, version="v1", is_default=True
        )

        this_org_versions = await version_service.list_for_service(organization_id, service.id)
        assert this_org_versions[0].is_default is True


class TestListForService:
    async def test_orders_by_version_string(
        self, version_service: VersionService, organization_id: uuid.UUID, make_service
    ) -> None:
        service = await make_service()
        await version_service.register(organization_id, service_id=service.id, version="v2")
        await version_service.register(organization_id, service_id=service.id, version="v1")
        await version_service.register(organization_id, service_id=service.id, version="v3")

        versions = await version_service.list_for_service(organization_id, service.id)
        assert [v.version_label for v in versions] == ["v1", "v2", "v3"]

    async def test_scoped_to_service(
        self, version_service: VersionService, organization_id: uuid.UUID, make_service
    ) -> None:
        service_a = await make_service(name="service-a")
        service_b = await make_service(name="service-b")
        await version_service.register(organization_id, service_id=service_a.id, version="v1")
        await version_service.register(organization_id, service_id=service_b.id, version="v1")

        a_versions = await version_service.list_for_service(organization_id, service_a.id)
        assert len(a_versions) == 1
        assert a_versions[0].service_id == service_a.id

    async def test_tenant_isolation(
        self, version_service: VersionService, organization_id: uuid.UUID, make_service
    ) -> None:
        service = await make_service()
        await version_service.register(organization_id, service_id=service.id, version="v1")

        found = await version_service.list_for_service(uuid.uuid4(), service.id)
        assert found == []


class TestDeprecate:
    async def test_sets_deprecation_fields(
        self, version_service: VersionService, organization_id: uuid.UUID, make_service
    ) -> None:
        service = await make_service()
        created = await version_service.register(
            organization_id, service_id=service.id, version="v1"
        )
        sunset = soon(86400)
        updated = await version_service.deprecate(
            organization_id, created.id, message="Use v2 instead.", sunset_at=sunset
        )
        assert updated.is_deprecated is True
        assert updated.deprecation_message == "Use v2 instead."
        assert updated.sunset_at == sunset

    async def test_defaults_leave_message_and_sunset_unset(
        self, version_service: VersionService, organization_id: uuid.UUID, make_service
    ) -> None:
        service = await make_service()
        created = await version_service.register(
            organization_id, service_id=service.id, version="v1"
        )
        updated = await version_service.deprecate(organization_id, created.id)
        assert updated.is_deprecated is True
        assert updated.deprecation_message is None
        assert updated.sunset_at is None

    async def test_always_overwrites_rather_than_merging(
        self, version_service: VersionService, organization_id: uuid.UUID, make_service
    ) -> None:
        """Unlike ``update()``, ``deprecate()`` has no "only if not None" guard --
        a second call without a message genuinely clears the first one."""
        service = await make_service()
        created = await version_service.register(
            organization_id, service_id=service.id, version="v1"
        )
        await version_service.deprecate(organization_id, created.id, message="First message.")
        updated_again = await version_service.deprecate(organization_id, created.id)
        assert updated_again.deprecation_message is None

    async def test_raises_not_found_for_a_missing_id(
        self, version_service: VersionService, organization_id: uuid.UUID
    ) -> None:
        with pytest.raises(NotFoundError):
            await version_service.deprecate(organization_id, uuid.uuid4())

    async def test_raises_not_found_for_a_cross_org_id(
        self, version_service: VersionService, organization_id: uuid.UUID, make_service
    ) -> None:
        """Regression test for a genuine tenant-isolation bug: ``deprecate()``
        looked the version up by the base repository's unscoped ``require_by_id``
        instead of the tenant-scoped ``require_in_org``, so any organization
        could deprecate any other organization's version by id. Fixed in
        ``app/repositories/version.py`` (added ``require_in_org``) and
        ``app/services/version.py`` (``deprecate`` now calls it)."""
        service = await make_service()
        created = await version_service.register(
            organization_id, service_id=service.id, version="v1"
        )
        other_org = uuid.uuid4()
        with pytest.raises(NotFoundError):
            await version_service.deprecate(other_org, created.id)

        # And the version itself must remain untouched by the attempt.
        untouched = await version_service.list_for_service(organization_id, service.id)
        assert untouched[0].is_deprecated is False


class TestApiVersionRepository:
    """Direct repository-level coverage for paths no service method reaches."""

    async def test_require_in_org_returns_the_matching_row(
        self,
        versions_repo: ApiVersionRepository,
        version_service: VersionService,
        organization_id: uuid.UUID,
        make_service,
    ) -> None:
        service = await make_service()
        created = await version_service.register(
            organization_id, service_id=service.id, version="v1"
        )
        found = await versions_repo.require_in_org(organization_id, created.id)
        assert found.id == created.id

    async def test_require_in_org_raises_not_found_for_unknown_id(
        self, versions_repo: ApiVersionRepository, organization_id: uuid.UUID
    ) -> None:
        with pytest.raises(NotFoundError):
            await versions_repo.require_in_org(organization_id, uuid.uuid4())

    async def test_require_in_org_raises_not_found_for_other_org(
        self,
        versions_repo: ApiVersionRepository,
        version_service: VersionService,
        organization_id: uuid.UUID,
        make_service,
    ) -> None:
        service = await make_service()
        created = await version_service.register(
            organization_id, service_id=service.id, version="v1"
        )
        with pytest.raises(NotFoundError):
            await versions_repo.require_in_org(uuid.uuid4(), created.id)

    async def test_get_default_returns_none_when_no_default_set(
        self,
        versions_repo: ApiVersionRepository,
        version_service: VersionService,
        organization_id: uuid.UUID,
        make_service,
    ) -> None:
        service = await make_service()
        await version_service.register(organization_id, service_id=service.id, version="v1")
        found = await versions_repo.get_default(organization_id, service.id)
        assert found is None
