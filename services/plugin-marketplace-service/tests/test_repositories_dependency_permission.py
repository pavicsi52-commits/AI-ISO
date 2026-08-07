"""Repository tests for ``PluginDependencyRepository`` and ``PluginPermissionRepository``."""

from __future__ import annotations

import uuid

from app.models.dependency import PluginDependency
from app.models.enums import (
    PermissionGrantStatus,
    PluginCategory,
    PluginPermissionCategory,
    PluginType,
)
from app.models.installation import PluginInstallation
from app.models.permission import PluginPermissionGrant
from app.models.plugin import Plugin
from app.repositories.dependency import PluginDependencyRepository
from app.repositories.installation import PluginInstallationRepository
from app.repositories.permission import PluginPermissionRepository
from app.repositories.plugin import PluginRepository
from tests.conftest import utcnow


def _plugin(organization_id: uuid.UUID, *, slug: str = "plugin", **kwargs: object) -> Plugin:
    defaults: dict[str, object] = {
        "organization_id": organization_id,
        "slug": slug,
        "name": "Test Plugin",
        "category": PluginCategory.UTILITIES,
        "plugin_type": PluginType.CUSTOM_PLUGIN,
    }
    defaults.update(kwargs)
    return Plugin(**defaults)


def _dependency(plugin: Plugin, depends_on: Plugin, **kwargs: object) -> PluginDependency:
    defaults: dict[str, object] = {
        "organization_id": plugin.organization_id,
        "plugin_id": plugin.id,
        "depends_on_plugin_id": depends_on.id,
    }
    defaults.update(kwargs)
    return PluginDependency(**defaults)


def _installation(plugin: Plugin, **kwargs: object) -> PluginInstallation:
    defaults: dict[str, object] = {
        "organization_id": plugin.organization_id,
        "plugin_id": plugin.id,
        "installed_version_number": "1.0.0",
        "installed_at": utcnow(),
    }
    defaults.update(kwargs)
    return PluginInstallation(**defaults)


def _permission(
    installation: PluginInstallation,
    *,
    category: PluginPermissionCategory = PluginPermissionCategory.INVENTORY,
    **kwargs: object,
) -> PluginPermissionGrant:
    defaults: dict[str, object] = {
        "organization_id": installation.organization_id,
        "plugin_installation_id": installation.id,
        "category": category,
    }
    defaults.update(kwargs)
    return PluginPermissionGrant(**defaults)


class TestPluginDependencyRepository:
    async def test_create_and_require_by_id_round_trip(
        self,
        plugins_repo: PluginRepository,
        dependencies_repo: PluginDependencyRepository,
        organization_id: uuid.UUID,
    ) -> None:
        core = await plugins_repo.create(_plugin(organization_id, slug="core"))
        addon = await plugins_repo.create(_plugin(organization_id, slug="addon"))
        created = await dependencies_repo.create(_dependency(addon, core))
        fetched = await dependencies_repo.require_by_id(created.id)
        assert fetched.id == created.id

    async def test_list_for_plugin(
        self,
        plugins_repo: PluginRepository,
        dependencies_repo: PluginDependencyRepository,
        organization_id: uuid.UUID,
    ) -> None:
        addon = await plugins_repo.create(_plugin(organization_id, slug="addon"))
        core_a = await plugins_repo.create(_plugin(organization_id, slug="core-a"))
        core_b = await plugins_repo.create(_plugin(organization_id, slug="core-b"))
        edge_a = await dependencies_repo.create(_dependency(addon, core_a))
        edge_b = await dependencies_repo.create(_dependency(addon, core_b))

        found = await dependencies_repo.list_for_plugin(addon.id)
        assert {d.id for d in found} == {edge_a.id, edge_b.id}

    async def test_list_for_plugin_empty(
        self, dependencies_repo: PluginDependencyRepository
    ) -> None:
        assert await dependencies_repo.list_for_plugin(uuid.uuid4()) == []

    async def test_list_dependents(
        self,
        plugins_repo: PluginRepository,
        dependencies_repo: PluginDependencyRepository,
        organization_id: uuid.UUID,
    ) -> None:
        core = await plugins_repo.create(_plugin(organization_id, slug="core"))
        addon_a = await plugins_repo.create(_plugin(organization_id, slug="addon-a"))
        addon_b = await plugins_repo.create(_plugin(organization_id, slug="addon-b"))
        edge_a = await dependencies_repo.create(_dependency(addon_a, core))
        edge_b = await dependencies_repo.create(_dependency(addon_b, core))

        found = await dependencies_repo.list_dependents(core.id)
        assert {d.id for d in found} == {edge_a.id, edge_b.id}

    async def test_list_dependents_empty(
        self, dependencies_repo: PluginDependencyRepository
    ) -> None:
        assert await dependencies_repo.list_dependents(uuid.uuid4()) == []

    async def test_list_all_edges_scoped_by_org(
        self,
        plugins_repo: PluginRepository,
        dependencies_repo: PluginDependencyRepository,
        organization_id: uuid.UUID,
    ) -> None:
        other_org = uuid.uuid4()
        addon = await plugins_repo.create(_plugin(organization_id, slug="addon"))
        core = await plugins_repo.create(_plugin(organization_id, slug="core"))
        own_edge = await dependencies_repo.create(_dependency(addon, core))

        other_addon = await plugins_repo.create(_plugin(other_org, slug="addon"))
        other_core = await plugins_repo.create(_plugin(other_org, slug="core"))
        await dependencies_repo.create(_dependency(other_addon, other_core))

        found = await dependencies_repo.list_all_edges(organization_id)
        assert [d.id for d in found] == [own_edge.id]

    async def test_list_all_edges_empty(
        self, dependencies_repo: PluginDependencyRepository, organization_id: uuid.UUID
    ) -> None:
        assert await dependencies_repo.list_all_edges(organization_id) == []


class TestPluginPermissionRepository:
    async def test_create_and_require_by_id_round_trip(
        self,
        plugins_repo: PluginRepository,
        installations_repo: PluginInstallationRepository,
        permissions_repo: PluginPermissionRepository,
        organization_id: uuid.UUID,
    ) -> None:
        plugin = await plugins_repo.create(_plugin(organization_id, slug="perm-round"))
        installation = await installations_repo.create(_installation(plugin))
        created = await permissions_repo.create(_permission(installation))
        fetched = await permissions_repo.require_by_id(created.id)
        assert fetched.id == created.id

    async def test_list_for_installation(
        self,
        plugins_repo: PluginRepository,
        installations_repo: PluginInstallationRepository,
        permissions_repo: PluginPermissionRepository,
        organization_id: uuid.UUID,
    ) -> None:
        plugin = await plugins_repo.create(_plugin(organization_id, slug="perm-list"))
        installation = await installations_repo.create(_installation(plugin))
        grant_a = await permissions_repo.create(
            _permission(installation, category=PluginPermissionCategory.INVENTORY)
        )
        grant_b = await permissions_repo.create(
            _permission(installation, category=PluginPermissionCategory.NETWORK)
        )

        found = await permissions_repo.list_for_installation(installation.id)
        assert {g.id for g in found} == {grant_a.id, grant_b.id}

    async def test_list_for_installation_empty(
        self, permissions_repo: PluginPermissionRepository
    ) -> None:
        assert await permissions_repo.list_for_installation(uuid.uuid4()) == []

    async def test_list_granted_only_granted_status(
        self,
        plugins_repo: PluginRepository,
        installations_repo: PluginInstallationRepository,
        permissions_repo: PluginPermissionRepository,
        organization_id: uuid.UUID,
    ) -> None:
        plugin = await plugins_repo.create(_plugin(organization_id, slug="perm-granted"))
        installation = await installations_repo.create(_installation(plugin))
        granted = await permissions_repo.create(
            _permission(
                installation,
                category=PluginPermissionCategory.INVENTORY,
                status=PermissionGrantStatus.GRANTED,
            )
        )
        await permissions_repo.create(
            _permission(
                installation,
                category=PluginPermissionCategory.NETWORK,
                status=PermissionGrantStatus.PENDING,
            )
        )
        await permissions_repo.create(
            _permission(
                installation,
                category=PluginPermissionCategory.SECRETS,
                status=PermissionGrantStatus.DENIED,
            )
        )

        found = await permissions_repo.list_granted(installation.id)
        assert [g.id for g in found] == [granted.id]

    async def test_list_granted_empty(
        self,
        plugins_repo: PluginRepository,
        installations_repo: PluginInstallationRepository,
        permissions_repo: PluginPermissionRepository,
        organization_id: uuid.UUID,
    ) -> None:
        plugin = await plugins_repo.create(_plugin(organization_id, slug="perm-nogrant"))
        installation = await installations_repo.create(_installation(plugin))
        await permissions_repo.create(
            _permission(
                installation,
                category=PluginPermissionCategory.INVENTORY,
                status=PermissionGrantStatus.PENDING,
            )
        )

        assert await permissions_repo.list_granted(installation.id) == []

    async def test_get_for_category_hit(
        self,
        plugins_repo: PluginRepository,
        installations_repo: PluginInstallationRepository,
        permissions_repo: PluginPermissionRepository,
        organization_id: uuid.UUID,
    ) -> None:
        plugin = await plugins_repo.create(_plugin(organization_id, slug="perm-cat"))
        installation = await installations_repo.create(_installation(plugin))
        grant = await permissions_repo.create(
            _permission(installation, category=PluginPermissionCategory.MONITORING)
        )

        found = await permissions_repo.get_for_category(
            installation.id, PluginPermissionCategory.MONITORING
        )
        assert found is not None
        assert found.id == grant.id

    async def test_get_for_category_miss(
        self,
        plugins_repo: PluginRepository,
        installations_repo: PluginInstallationRepository,
        permissions_repo: PluginPermissionRepository,
        organization_id: uuid.UUID,
    ) -> None:
        plugin = await plugins_repo.create(_plugin(organization_id, slug="perm-nocat"))
        installation = await installations_repo.create(_installation(plugin))

        found = await permissions_repo.get_for_category(
            installation.id, PluginPermissionCategory.API
        )
        assert found is None
