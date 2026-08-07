"""Repository tests for ``PluginManifestRepository`` and ``PluginPackageRepository``."""

from __future__ import annotations

import uuid

from app.models.enums import PluginCategory, PluginType
from app.models.manifest import PluginManifestEntry
from app.models.package import PluginPackage
from app.models.plugin import Plugin, PluginVersion
from app.repositories.manifest import PluginManifestRepository
from app.repositories.package import PluginPackageRepository
from app.repositories.plugin import PluginRepository, PluginVersionRepository
from tests.conftest import ago, utcnow


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


def _version(plugin: Plugin, *, version_number: str = "1.0.0", **kwargs: object) -> PluginVersion:
    defaults: dict[str, object] = {
        "organization_id": plugin.organization_id,
        "plugin_id": plugin.id,
        "version_number": version_number,
        "released_at": utcnow(),
    }
    defaults.update(kwargs)
    return PluginVersion(**defaults)


def _manifest(plugin: Plugin, version: PluginVersion, **kwargs: object) -> PluginManifestEntry:
    defaults: dict[str, object] = {
        "organization_id": plugin.organization_id,
        "plugin_id": plugin.id,
        "plugin_version_id": version.id,
    }
    defaults.update(kwargs)
    return PluginManifestEntry(**defaults)


def _package(
    plugin: Plugin, version: PluginVersion, *, checksum: str = "deadbeef", **kwargs: object
) -> PluginPackage:
    defaults: dict[str, object] = {
        "organization_id": plugin.organization_id,
        "plugin_id": plugin.id,
        "plugin_version_id": version.id,
        "storage_key": f"packages/{version.id}.tar.gz",
        "size_bytes": 2048,
        "checksum": checksum,
    }
    defaults.update(kwargs)
    return PluginPackage(**defaults)


class TestPluginManifestRepository:
    async def test_create_and_require_by_id_round_trip(
        self,
        plugins_repo: PluginRepository,
        versions_repo: PluginVersionRepository,
        manifests_repo: PluginManifestRepository,
        organization_id: uuid.UUID,
    ) -> None:
        plugin = await plugins_repo.create(_plugin(organization_id, slug="m-round"))
        version = await versions_repo.create(_version(plugin))
        created = await manifests_repo.create(_manifest(plugin, version, checksum="abc123"))
        fetched = await manifests_repo.require_by_id(created.id)
        assert fetched.id == created.id
        assert fetched.checksum == "abc123"

    async def test_get_for_version_hit(
        self,
        plugins_repo: PluginRepository,
        versions_repo: PluginVersionRepository,
        manifests_repo: PluginManifestRepository,
        organization_id: uuid.UUID,
    ) -> None:
        plugin = await plugins_repo.create(_plugin(organization_id, slug="m-hit"))
        version = await versions_repo.create(_version(plugin))
        manifest = await manifests_repo.create(_manifest(plugin, version))

        found = await manifests_repo.get_for_version(version.id)
        assert found is not None
        assert found.id == manifest.id

    async def test_get_for_version_miss(self, manifests_repo: PluginManifestRepository) -> None:
        assert await manifests_repo.get_for_version(uuid.uuid4()) is None

    async def test_list_for_plugin(
        self,
        plugins_repo: PluginRepository,
        versions_repo: PluginVersionRepository,
        manifests_repo: PluginManifestRepository,
        organization_id: uuid.UUID,
    ) -> None:
        plugin = await plugins_repo.create(_plugin(organization_id, slug="m-list"))
        v1 = await versions_repo.create(_version(plugin, version_number="1.0.0"))
        v2 = await versions_repo.create(_version(plugin, version_number="2.0.0"))
        older = await manifests_repo.create(_manifest(plugin, v1, created_at=ago(200)))
        newer = await manifests_repo.create(_manifest(plugin, v2, created_at=ago(10)))

        found = await manifests_repo.list_for_plugin(plugin.id)
        assert [m.id for m in found] == [newer.id, older.id]

    async def test_list_for_plugin_empty(self, manifests_repo: PluginManifestRepository) -> None:
        assert await manifests_repo.list_for_plugin(uuid.uuid4()) == []


class TestPluginPackageRepository:
    async def test_create_and_require_by_id_round_trip(
        self,
        plugins_repo: PluginRepository,
        versions_repo: PluginVersionRepository,
        packages_repo: PluginPackageRepository,
        organization_id: uuid.UUID,
    ) -> None:
        plugin = await plugins_repo.create(_plugin(organization_id, slug="pkg-round"))
        version = await versions_repo.create(_version(plugin))
        created = await packages_repo.create(_package(plugin, version, checksum="round-trip-sum"))
        fetched = await packages_repo.require_by_id(created.id)
        assert fetched.id == created.id
        assert fetched.checksum == "round-trip-sum"

    async def test_get_for_version_hit(
        self,
        plugins_repo: PluginRepository,
        versions_repo: PluginVersionRepository,
        packages_repo: PluginPackageRepository,
        organization_id: uuid.UUID,
    ) -> None:
        plugin = await plugins_repo.create(_plugin(organization_id, slug="pkg-hit"))
        version = await versions_repo.create(_version(plugin))
        package = await packages_repo.create(_package(plugin, version))

        found = await packages_repo.get_for_version(version.id)
        assert found is not None
        assert found.id == package.id

    async def test_get_for_version_miss(self, packages_repo: PluginPackageRepository) -> None:
        assert await packages_repo.get_for_version(uuid.uuid4()) is None

    async def test_get_by_checksum_hit(
        self,
        plugins_repo: PluginRepository,
        versions_repo: PluginVersionRepository,
        packages_repo: PluginPackageRepository,
        organization_id: uuid.UUID,
    ) -> None:
        plugin = await plugins_repo.create(_plugin(organization_id, slug="pkg-checksum"))
        version = await versions_repo.create(_version(plugin))
        package = await packages_repo.create(
            _package(plugin, version, checksum="sha256:unique-value")
        )

        found = await packages_repo.get_by_checksum("sha256:unique-value")
        assert found is not None
        assert found.id == package.id

    async def test_get_by_checksum_miss(self, packages_repo: PluginPackageRepository) -> None:
        assert await packages_repo.get_by_checksum("does-not-exist") is None
