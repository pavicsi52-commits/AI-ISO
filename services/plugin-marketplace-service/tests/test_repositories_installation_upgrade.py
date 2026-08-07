"""Repository tests for ``PluginInstallationRepository``, ``PluginUpgradeRepository``,
and ``PluginRollbackRepository``.
"""

from __future__ import annotations

import uuid

import pytest
from shared_core.exceptions.not_found import NotFoundError

from app.models.enums import PluginCategory, PluginInstallationStatus, PluginType
from app.models.installation import PluginInstallation
from app.models.plugin import Plugin
from app.models.upgrade import PluginRollback, PluginUpgrade
from app.repositories.installation import PluginInstallationRepository
from app.repositories.plugin import PluginRepository
from app.repositories.upgrade import PluginRollbackRepository, PluginUpgradeRepository
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


def _installation(plugin: Plugin, **kwargs: object) -> PluginInstallation:
    defaults: dict[str, object] = {
        "organization_id": plugin.organization_id,
        "plugin_id": plugin.id,
        "installed_version_number": "1.0.0",
        "installed_at": utcnow(),
    }
    defaults.update(kwargs)
    return PluginInstallation(**defaults)


def _upgrade(
    installation: PluginInstallation,
    *,
    from_version: str = "1.0.0",
    to_version: str = "2.0.0",
    **kwargs: object,
) -> PluginUpgrade:
    defaults: dict[str, object] = {
        "organization_id": installation.organization_id,
        "plugin_installation_id": installation.id,
        "from_version_number": from_version,
        "to_version_number": to_version,
        "started_at": utcnow(),
    }
    defaults.update(kwargs)
    return PluginUpgrade(**defaults)


def _rollback(
    installation: PluginInstallation,
    *,
    from_version: str = "2.0.0",
    to_version: str = "1.0.0",
    **kwargs: object,
) -> PluginRollback:
    defaults: dict[str, object] = {
        "organization_id": installation.organization_id,
        "plugin_installation_id": installation.id,
        "from_version_number": from_version,
        "to_version_number": to_version,
        "started_at": utcnow(),
    }
    defaults.update(kwargs)
    return PluginRollback(**defaults)


class TestPluginInstallationRepository:
    async def test_create_and_require_by_id_round_trip(
        self,
        plugins_repo: PluginRepository,
        installations_repo: PluginInstallationRepository,
        organization_id: uuid.UUID,
    ) -> None:
        plugin = await plugins_repo.create(_plugin(organization_id, slug="inst-round"))
        created = await installations_repo.create(_installation(plugin))
        fetched = await installations_repo.require_by_id(created.id)
        assert fetched.id == created.id

    async def test_require_in_org_hit(
        self,
        plugins_repo: PluginRepository,
        installations_repo: PluginInstallationRepository,
        organization_id: uuid.UUID,
    ) -> None:
        plugin = await plugins_repo.create(_plugin(organization_id, slug="inst-hit"))
        installation = await installations_repo.create(_installation(plugin))
        found = await installations_repo.require_in_org(organization_id, installation.id)
        assert found.id == installation.id

    async def test_require_in_org_miss_unknown_id(
        self, installations_repo: PluginInstallationRepository, organization_id: uuid.UUID
    ) -> None:
        with pytest.raises(NotFoundError):
            await installations_repo.require_in_org(organization_id, uuid.uuid4())

    async def test_require_in_org_miss_wrong_org(
        self,
        plugins_repo: PluginRepository,
        installations_repo: PluginInstallationRepository,
        organization_id: uuid.UUID,
    ) -> None:
        plugin = await plugins_repo.create(_plugin(organization_id, slug="inst-wrong-org"))
        installation = await installations_repo.create(_installation(plugin))
        with pytest.raises(NotFoundError):
            await installations_repo.require_in_org(uuid.uuid4(), installation.id)

    async def test_get_for_plugin_hit(
        self,
        plugins_repo: PluginRepository,
        installations_repo: PluginInstallationRepository,
        organization_id: uuid.UUID,
    ) -> None:
        plugin = await plugins_repo.create(_plugin(organization_id, slug="inst-get"))
        installation = await installations_repo.create(_installation(plugin))

        found = await installations_repo.get_for_plugin(organization_id, plugin.id)
        assert found is not None
        assert found.id == installation.id

    async def test_get_for_plugin_miss(
        self,
        plugins_repo: PluginRepository,
        installations_repo: PluginInstallationRepository,
        organization_id: uuid.UUID,
    ) -> None:
        plugin = await plugins_repo.create(_plugin(organization_id, slug="inst-noget"))
        assert await installations_repo.get_for_plugin(organization_id, plugin.id) is None

    async def test_list_for_org_status_filter(
        self,
        plugins_repo: PluginRepository,
        installations_repo: PluginInstallationRepository,
        organization_id: uuid.UUID,
    ) -> None:
        plugin_a = await plugins_repo.create(_plugin(organization_id, slug="inst-a"))
        plugin_b = await plugins_repo.create(_plugin(organization_id, slug="inst-b"))
        active = await installations_repo.create(
            _installation(plugin_a, status=PluginInstallationStatus.ACTIVE)
        )
        disabled = await installations_repo.create(
            _installation(plugin_b, status=PluginInstallationStatus.DISABLED)
        )

        active_only = await installations_repo.list_for_org(
            organization_id, status=PluginInstallationStatus.ACTIVE
        )
        assert [i.id for i in active_only] == [active.id]

        all_installations = await installations_repo.list_for_org(organization_id)
        assert {i.id for i in all_installations} == {active.id, disabled.id}

    async def test_list_for_org_empty(
        self, installations_repo: PluginInstallationRepository, organization_id: uuid.UUID
    ) -> None:
        assert await installations_repo.list_for_org(organization_id) == []

    async def test_list_active_for_plugin_across_orgs(
        self,
        plugins_repo: PluginRepository,
        installations_repo: PluginInstallationRepository,
        organization_id: uuid.UUID,
    ) -> None:
        other_org = uuid.uuid4()
        plugin = await plugins_repo.create(_plugin(organization_id, slug="cross-org-plugin"))
        active_a = await installations_repo.create(
            _installation(plugin, status=PluginInstallationStatus.ACTIVE)
        )
        active_b = await installations_repo.create(
            _installation(
                plugin, organization_id=other_org, status=PluginInstallationStatus.ACTIVE
            )
        )
        await installations_repo.create(
            _installation(
                plugin, organization_id=uuid.uuid4(), status=PluginInstallationStatus.DISABLED
            )
        )

        found = await installations_repo.list_active_for_plugin(plugin.id)
        assert {i.id for i in found} == {active_a.id, active_b.id}

    async def test_list_active_for_plugin_empty(
        self, installations_repo: PluginInstallationRepository
    ) -> None:
        assert await installations_repo.list_active_for_plugin(uuid.uuid4()) == []

    async def test_list_all_active(
        self,
        plugins_repo: PluginRepository,
        installations_repo: PluginInstallationRepository,
        organization_id: uuid.UUID,
    ) -> None:
        plugin_a = await plugins_repo.create(_plugin(organization_id, slug="all-active-a"))
        plugin_b = await plugins_repo.create(_plugin(organization_id, slug="all-active-b"))
        active_a = await installations_repo.create(
            _installation(plugin_a, status=PluginInstallationStatus.ACTIVE)
        )
        active_b = await installations_repo.create(
            _installation(plugin_b, status=PluginInstallationStatus.ACTIVE)
        )
        disabled = await installations_repo.create(
            _installation(
                plugin_a, organization_id=uuid.uuid4(), status=PluginInstallationStatus.DISABLED
            )
        )

        found = await installations_repo.list_all_active()
        found_ids = {i.id for i in found}
        assert {active_a.id, active_b.id}.issubset(found_ids)
        assert disabled.id not in found_ids


class TestPluginUpgradeRepository:
    async def test_create_and_require_by_id_round_trip(
        self,
        plugins_repo: PluginRepository,
        installations_repo: PluginInstallationRepository,
        upgrades_repo: PluginUpgradeRepository,
        organization_id: uuid.UUID,
    ) -> None:
        plugin = await plugins_repo.create(_plugin(organization_id, slug="upg-round"))
        installation = await installations_repo.create(_installation(plugin))
        created = await upgrades_repo.create(_upgrade(installation))
        fetched = await upgrades_repo.require_by_id(created.id)
        assert fetched.id == created.id

    async def test_list_for_installation_ordering_newest_first(
        self,
        plugins_repo: PluginRepository,
        installations_repo: PluginInstallationRepository,
        upgrades_repo: PluginUpgradeRepository,
        organization_id: uuid.UUID,
    ) -> None:
        plugin = await plugins_repo.create(_plugin(organization_id, slug="upg-order"))
        installation = await installations_repo.create(_installation(plugin))
        oldest = await upgrades_repo.create(
            _upgrade(
                installation, from_version="1.0.0", to_version="1.1.0", started_at=ago(300)
            )
        )
        newest = await upgrades_repo.create(
            _upgrade(
                installation, from_version="1.1.0", to_version="1.2.0", started_at=ago(10)
            )
        )
        middle = await upgrades_repo.create(
            _upgrade(
                installation, from_version="1.2.0", to_version="1.3.0", started_at=ago(150)
            )
        )

        found = await upgrades_repo.list_for_installation(installation.id)
        assert [u.id for u in found] == [newest.id, middle.id, oldest.id]

    async def test_list_for_installation_empty(
        self, upgrades_repo: PluginUpgradeRepository
    ) -> None:
        assert await upgrades_repo.list_for_installation(uuid.uuid4()) == []


class TestPluginRollbackRepository:
    async def test_create_and_require_by_id_round_trip(
        self,
        plugins_repo: PluginRepository,
        installations_repo: PluginInstallationRepository,
        rollbacks_repo: PluginRollbackRepository,
        organization_id: uuid.UUID,
    ) -> None:
        plugin = await plugins_repo.create(_plugin(organization_id, slug="rb-round"))
        installation = await installations_repo.create(_installation(plugin))
        created = await rollbacks_repo.create(_rollback(installation))
        fetched = await rollbacks_repo.require_by_id(created.id)
        assert fetched.id == created.id

    async def test_list_for_installation_ordering_newest_first(
        self,
        plugins_repo: PluginRepository,
        installations_repo: PluginInstallationRepository,
        rollbacks_repo: PluginRollbackRepository,
        organization_id: uuid.UUID,
    ) -> None:
        plugin = await plugins_repo.create(_plugin(organization_id, slug="rb-order"))
        installation = await installations_repo.create(_installation(plugin))
        oldest = await rollbacks_repo.create(_rollback(installation, started_at=ago(300)))
        newest = await rollbacks_repo.create(_rollback(installation, started_at=ago(10)))
        middle = await rollbacks_repo.create(_rollback(installation, started_at=ago(150)))

        found = await rollbacks_repo.list_for_installation(installation.id)
        assert [r.id for r in found] == [newest.id, middle.id, oldest.id]

    async def test_list_for_installation_empty(
        self, rollbacks_repo: PluginRollbackRepository
    ) -> None:
        assert await rollbacks_repo.list_for_installation(uuid.uuid4()) == []
