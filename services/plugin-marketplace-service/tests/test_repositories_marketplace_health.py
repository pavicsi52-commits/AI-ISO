"""Repository tests for ``PluginMarketplaceRepository`` and ``PluginHealthRepository``."""

from __future__ import annotations

import uuid

from shared_core.enums.health_status import HealthStatus

from app.models.enums import MarketplaceListingStatus, PluginCategory, PluginType
from app.models.health import PluginHealth
from app.models.installation import PluginInstallation
from app.models.marketplace import PluginMarketplaceEntry
from app.models.plugin import Plugin
from app.repositories.health import PluginHealthRepository
from app.repositories.installation import PluginInstallationRepository
from app.repositories.marketplace import PluginMarketplaceRepository
from app.repositories.plugin import PluginRepository
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


def _marketplace(plugin: Plugin, **kwargs: object) -> PluginMarketplaceEntry:
    defaults: dict[str, object] = {
        "organization_id": plugin.organization_id,
        "plugin_id": plugin.id,
        "status": MarketplaceListingStatus.PUBLISHED,
    }
    defaults.update(kwargs)
    return PluginMarketplaceEntry(**defaults)


def _installation(plugin: Plugin, **kwargs: object) -> PluginInstallation:
    defaults: dict[str, object] = {
        "organization_id": plugin.organization_id,
        "plugin_id": plugin.id,
        "installed_version_number": "1.0.0",
        "installed_at": utcnow(),
    }
    defaults.update(kwargs)
    return PluginInstallation(**defaults)


def _health(installation: PluginInstallation, **kwargs: object) -> PluginHealth:
    defaults: dict[str, object] = {
        "organization_id": installation.organization_id,
        "plugin_installation_id": installation.id,
        "checked_at": utcnow(),
    }
    defaults.update(kwargs)
    return PluginHealth(**defaults)


class TestPluginMarketplaceRepository:
    async def test_create_and_require_by_id_round_trip(
        self,
        plugins_repo: PluginRepository,
        marketplace_repo: PluginMarketplaceRepository,
        organization_id: uuid.UUID,
    ) -> None:
        plugin = await plugins_repo.create(_plugin(organization_id, slug="mkt-round"))
        created = await marketplace_repo.create(_marketplace(plugin))
        fetched = await marketplace_repo.require_by_id(created.id)
        assert fetched.id == created.id

    async def test_get_for_plugin_hit(
        self,
        plugins_repo: PluginRepository,
        marketplace_repo: PluginMarketplaceRepository,
        organization_id: uuid.UUID,
    ) -> None:
        plugin = await plugins_repo.create(_plugin(organization_id, slug="mkt-hit"))
        entry = await marketplace_repo.create(_marketplace(plugin))

        found = await marketplace_repo.get_for_plugin(plugin.id)
        assert found is not None
        assert found.id == entry.id

    async def test_get_for_plugin_miss(self, marketplace_repo: PluginMarketplaceRepository) -> None:
        assert await marketplace_repo.get_for_plugin(uuid.uuid4()) is None

    async def test_list_published_search_matches_pricing_summary(
        self,
        plugins_repo: PluginRepository,
        marketplace_repo: PluginMarketplaceRepository,
        organization_id: uuid.UUID,
    ) -> None:
        """``search`` must match against ``pricing_summary`` even when the
        keyword never appears in ``search_keywords``.
        """
        plugin = await plugins_repo.create(_plugin(organization_id, slug="mkt-pricing"))
        entry = await marketplace_repo.create(
            _marketplace(
                plugin,
                pricing_summary="Turbocharged annual plan",
                search_keywords=["automation", "widgets"],
            )
        )

        found = await marketplace_repo.list_published(search="turbocharged")
        assert [e.id for e in found] == [entry.id]

    async def test_list_published_search_matches_search_keywords(
        self,
        plugins_repo: PluginRepository,
        marketplace_repo: PluginMarketplaceRepository,
        organization_id: uuid.UUID,
    ) -> None:
        """``search`` must also match against the JSON ``search_keywords``
        column even when the keyword never appears in ``pricing_summary``.
        """
        plugin = await plugins_repo.create(_plugin(organization_id, slug="mkt-keywords"))
        entry = await marketplace_repo.create(
            _marketplace(
                plugin,
                pricing_summary="Standard monthly plan",
                search_keywords=["zephyr-connector", "sync"],
            )
        )

        found = await marketplace_repo.list_published(search="zephyr")
        assert [e.id for e in found] == [entry.id]

    async def test_list_published_search_no_match(
        self,
        plugins_repo: PluginRepository,
        marketplace_repo: PluginMarketplaceRepository,
        organization_id: uuid.UUID,
    ) -> None:
        plugin = await plugins_repo.create(_plugin(organization_id, slug="mkt-nomatch"))
        await marketplace_repo.create(
            _marketplace(plugin, pricing_summary="Free tier", search_keywords=["basic"])
        )

        assert await marketplace_repo.list_published(search="nonexistent-term") == []

    async def test_list_published_excludes_draft(
        self,
        plugins_repo: PluginRepository,
        marketplace_repo: PluginMarketplaceRepository,
        organization_id: uuid.UUID,
    ) -> None:
        plugin = await plugins_repo.create(_plugin(organization_id, slug="mkt-draft"))
        await marketplace_repo.create(_marketplace(plugin, status=MarketplaceListingStatus.DRAFT))

        assert await marketplace_repo.list_published() == []

    async def test_list_published_featured_only(
        self,
        plugins_repo: PluginRepository,
        marketplace_repo: PluginMarketplaceRepository,
        organization_id: uuid.UUID,
    ) -> None:
        plugin_featured = await plugins_repo.create(_plugin(organization_id, slug="mkt-featured"))
        plugin_regular = await plugins_repo.create(_plugin(organization_id, slug="mkt-regular"))
        featured = await marketplace_repo.create(
            _marketplace(plugin_featured, status=MarketplaceListingStatus.FEATURED, featured=True)
        )
        await marketplace_repo.create(
            _marketplace(plugin_regular, status=MarketplaceListingStatus.PUBLISHED)
        )

        found = await marketplace_repo.list_published(featured_only=True)
        assert [e.id for e in found] == [featured.id]

        found_all = await marketplace_repo.list_published()
        assert len(found_all) == 2

    async def test_list_pending_approval(
        self,
        plugins_repo: PluginRepository,
        marketplace_repo: PluginMarketplaceRepository,
        organization_id: uuid.UUID,
    ) -> None:
        plugin_a = await plugins_repo.create(_plugin(organization_id, slug="mkt-pending-a"))
        plugin_b = await plugins_repo.create(_plugin(organization_id, slug="mkt-pending-b"))
        plugin_c = await plugins_repo.create(_plugin(organization_id, slug="mkt-pending-c"))
        older = await marketplace_repo.create(
            _marketplace(plugin_a, status=MarketplaceListingStatus.DRAFT, created_at=ago(200))
        )
        newer = await marketplace_repo.create(
            _marketplace(plugin_b, status=MarketplaceListingStatus.DRAFT, created_at=ago(10))
        )
        await marketplace_repo.create(
            _marketplace(plugin_c, status=MarketplaceListingStatus.PUBLISHED)
        )

        found = await marketplace_repo.list_pending_approval()
        assert [e.id for e in found] == [older.id, newer.id]

    async def test_list_pending_approval_empty(
        self, marketplace_repo: PluginMarketplaceRepository
    ) -> None:
        assert await marketplace_repo.list_pending_approval() == []


class TestPluginHealthRepository:
    async def test_create_and_require_by_id_round_trip(
        self,
        plugins_repo: PluginRepository,
        installations_repo: PluginInstallationRepository,
        health_repo: PluginHealthRepository,
        organization_id: uuid.UUID,
    ) -> None:
        plugin = await plugins_repo.create(_plugin(organization_id, slug="health-round"))
        installation = await installations_repo.create(_installation(plugin))
        created = await health_repo.create(_health(installation, status=HealthStatus.HEALTHY))
        fetched = await health_repo.require_by_id(created.id)
        assert fetched.id == created.id

    async def test_list_for_installation_ordering_newest_first(
        self,
        plugins_repo: PluginRepository,
        installations_repo: PluginInstallationRepository,
        health_repo: PluginHealthRepository,
        organization_id: uuid.UUID,
    ) -> None:
        plugin = await plugins_repo.create(_plugin(organization_id, slug="health-order"))
        installation = await installations_repo.create(_installation(plugin))
        oldest = await health_repo.create(_health(installation, checked_at=ago(300)))
        newest = await health_repo.create(_health(installation, checked_at=ago(10)))
        middle = await health_repo.create(_health(installation, checked_at=ago(150)))

        found = await health_repo.list_for_installation(installation.id)
        assert [h.id for h in found] == [newest.id, middle.id, oldest.id]

    async def test_list_for_installation_empty(self, health_repo: PluginHealthRepository) -> None:
        assert await health_repo.list_for_installation(uuid.uuid4()) == []

    async def test_get_latest_hit(
        self,
        plugins_repo: PluginRepository,
        installations_repo: PluginInstallationRepository,
        health_repo: PluginHealthRepository,
        organization_id: uuid.UUID,
    ) -> None:
        plugin = await plugins_repo.create(_plugin(organization_id, slug="health-latest"))
        installation = await installations_repo.create(_installation(plugin))
        await health_repo.create(_health(installation, checked_at=ago(300)))
        latest = await health_repo.create(_health(installation, checked_at=ago(10)))

        found = await health_repo.get_latest(installation.id)
        assert found is not None
        assert found.id == latest.id

    async def test_get_latest_miss(self, health_repo: PluginHealthRepository) -> None:
        assert await health_repo.get_latest(uuid.uuid4()) is None
