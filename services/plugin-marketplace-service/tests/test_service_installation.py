"""Tests for ``app.services.installation.PluginInstallationService``."""

from __future__ import annotations

import uuid
from typing import Any

import pytest
from shared_core.exceptions.validation import ValidationError

from app.manifests.engine import compute_manifest_checksum
from app.models.enums import (
    InstallationTrigger,
    PluginInstallationStatus,
    RollbackStatus,
    UpgradeStatus,
    UpgradeStrategy,
)
from app.repositories.dependency import PluginDependencyRepository
from app.repositories.upgrade import PluginRollbackRepository, PluginUpgradeRepository
from app.services.dependency import PluginDependencyService
from app.services.installation import PluginInstallationService
from app.services.plugin import PluginService
from tests.conftest import MakePluginFn, RecordingPublisher


def _manifest(
    version: str, *, category: str = "utilities", plugin_type: str = "custom_plugin"
) -> dict[str, Any]:
    manifest: dict[str, Any] = {
        "name": "Test Plugin",
        "publisher": "test-publisher",
        "category": category,
        "type": plugin_type,
        "version": version,
        "entry_points": ["main:run"],
        "supported_platform_versions": [
            {"platform": "aiios", "version_constraint": ">=1.0.0,<2.0.0"}
        ],
        "permissions_required": [],
        "dependencies": [],
        "api_requirements": [],
        "health_checks": [],
    }
    manifest["checksum"] = compute_manifest_checksum(manifest)
    return manifest


async def _publish_version(
    plugin_service: PluginService,
    organization_id: uuid.UUID,
    plugin_id: uuid.UUID,
    *,
    version_number: str,
) -> None:
    await plugin_service.submit_manifest(
        organization_id,
        plugin_id,
        version_number=version_number,
        manifest=_manifest(version_number),
    )
    await plugin_service.publish(organization_id, plugin_id, version_number=version_number)


async def _make_published_plugin(
    make_plugin: MakePluginFn,
    plugin_service: PluginService,
    organization_id: uuid.UUID,
    *,
    slug: str = "test-plugin",
    version_number: str = "1.0.0",
) -> Any:
    plugin = await make_plugin(slug=slug)
    await _publish_version(plugin_service, organization_id, plugin.id, version_number=version_number)
    return await plugin_service.get(organization_id, plugin.id)


# ---- install --------------------------------------------------------------


async def test_install_happy_path_emits_event(
    installation_service: PluginInstallationService,
    plugin_service: PluginService,
    make_plugin: MakePluginFn,
    organization_id: uuid.UUID,
    publisher: RecordingPublisher,
) -> None:
    plugin = await _make_published_plugin(make_plugin, plugin_service, organization_id)
    publisher.events.clear()

    installation = await installation_service.install(
        organization_id, plugin.id, installed_by="tester"
    )

    assert installation.status == PluginInstallationStatus.INSTALLED
    assert installation.installed_version_number == "1.0.0"
    assert installation.trigger == InstallationTrigger.ONLINE
    assert installation.installed_by == "tester"
    assert installation.installed_at is not None

    assert publisher.names == ["PluginInstalled"]
    event = publisher.events[0]
    assert event.organization_id == organization_id
    assert event.payload["installation_id"] == str(installation.id)
    assert event.payload["plugin_id"] == str(plugin.id)
    assert event.payload["version_number"] == "1.0.0"


async def test_install_without_published_version_raises(
    installation_service: PluginInstallationService,
    make_plugin: MakePluginFn,
    organization_id: uuid.UUID,
) -> None:
    plugin = await make_plugin(slug="unpublished-plugin")

    with pytest.raises(ValidationError):
        await installation_service.install(organization_id, plugin.id)


async def test_install_when_already_installed_raises(
    installation_service: PluginInstallationService,
    plugin_service: PluginService,
    make_plugin: MakePluginFn,
    organization_id: uuid.UUID,
) -> None:
    plugin = await _make_published_plugin(make_plugin, plugin_service, organization_id)
    await installation_service.install(organization_id, plugin.id)

    with pytest.raises(ValidationError):
        await installation_service.install(organization_id, plugin.id)


async def test_install_with_unmet_required_dependency_raises(
    installation_service: PluginInstallationService,
    plugin_service: PluginService,
    make_plugin: MakePluginFn,
    organization_id: uuid.UUID,
    dependencies_repo: PluginDependencyRepository,
) -> None:
    dependency_plugin = await _make_published_plugin(
        make_plugin, plugin_service, organization_id, slug="required-dependency"
    )
    dependent_plugin = await _make_published_plugin(
        make_plugin, plugin_service, organization_id, slug="dependent-plugin"
    )

    dependency_service = PluginDependencyService(dependencies_repo)
    await dependency_service.declare(
        organization_id,
        dependent_plugin.id,
        depends_on_plugin_id=dependency_plugin.id,
        optional=False,
    )

    with pytest.raises(ValidationError):
        await installation_service.install(organization_id, dependent_plugin.id)

    # Installing the dependency first, then the dependent, works.
    await installation_service.install(organization_id, dependency_plugin.id)
    installed = await installation_service.install(organization_id, dependent_plugin.id)
    assert installed.status == PluginInstallationStatus.INSTALLED


async def test_install_optional_dependency_does_not_block(
    installation_service: PluginInstallationService,
    plugin_service: PluginService,
    make_plugin: MakePluginFn,
    organization_id: uuid.UUID,
    dependencies_repo: PluginDependencyRepository,
) -> None:
    dependency_plugin = await _make_published_plugin(
        make_plugin, plugin_service, organization_id, slug="optional-dependency"
    )
    dependent_plugin = await _make_published_plugin(
        make_plugin, plugin_service, organization_id, slug="optional-dependent"
    )

    dependency_service = PluginDependencyService(dependencies_repo)
    await dependency_service.declare(
        organization_id,
        dependent_plugin.id,
        depends_on_plugin_id=dependency_plugin.id,
        optional=True,
    )

    installed = await installation_service.install(organization_id, dependent_plugin.id)
    assert installed.status == PluginInstallationStatus.INSTALLED


# ---- get / list -------------------------------------------------------------


async def test_get_returns_installation(
    installation_service: PluginInstallationService,
    plugin_service: PluginService,
    make_plugin: MakePluginFn,
    organization_id: uuid.UUID,
) -> None:
    plugin = await _make_published_plugin(make_plugin, plugin_service, organization_id)
    installed = await installation_service.install(organization_id, plugin.id)

    fetched = await installation_service.get(organization_id, installed.id)
    assert fetched.id == installed.id


async def test_list_for_org_with_status_filter(
    installation_service: PluginInstallationService,
    plugin_service: PluginService,
    make_plugin: MakePluginFn,
    organization_id: uuid.UUID,
) -> None:
    plugin_a = await _make_published_plugin(
        make_plugin, plugin_service, organization_id, slug="list-plugin-a"
    )
    plugin_b = await _make_published_plugin(
        make_plugin, plugin_service, organization_id, slug="list-plugin-b"
    )
    installed_a = await installation_service.install(organization_id, plugin_a.id)
    installed_b = await installation_service.install(organization_id, plugin_b.id)
    await installation_service.activate(organization_id, installed_b.id)

    all_installations = await installation_service.list_for_org(organization_id)
    assert {i.id for i in all_installations} == {installed_a.id, installed_b.id}

    installed_only = await installation_service.list_for_org(
        organization_id, status=PluginInstallationStatus.INSTALLED
    )
    assert {i.id for i in installed_only} == {installed_a.id}

    active_only = await installation_service.list_for_org(
        organization_id, status=PluginInstallationStatus.ACTIVE
    )
    assert {i.id for i in active_only} == {installed_b.id}


# ---- configure / activate / disable / remove --------------------------------


async def test_configure_updates_configuration_and_status(
    installation_service: PluginInstallationService,
    plugin_service: PluginService,
    make_plugin: MakePluginFn,
    organization_id: uuid.UUID,
) -> None:
    plugin = await _make_published_plugin(make_plugin, plugin_service, organization_id)
    installed = await installation_service.install(organization_id, plugin.id)

    configured = await installation_service.configure(
        organization_id, installed.id, configuration={"health_check_url": "http://example.test"}
    )

    assert configured.configuration == {"health_check_url": "http://example.test"}
    assert configured.status == PluginInstallationStatus.CONFIGURED


async def test_activate_sets_active_and_emits_event(
    installation_service: PluginInstallationService,
    plugin_service: PluginService,
    make_plugin: MakePluginFn,
    organization_id: uuid.UUID,
    publisher: RecordingPublisher,
) -> None:
    plugin = await _make_published_plugin(make_plugin, plugin_service, organization_id)
    installed = await installation_service.install(organization_id, plugin.id)
    publisher.events.clear()

    activated = await installation_service.activate(organization_id, installed.id)

    assert activated.status == PluginInstallationStatus.ACTIVE
    assert activated.activated_at is not None
    assert publisher.names == ["PluginActivated"]
    assert publisher.events[0].payload["installation_id"] == str(installed.id)


async def test_disable_sets_status_and_emits_event(
    installation_service: PluginInstallationService,
    plugin_service: PluginService,
    make_plugin: MakePluginFn,
    organization_id: uuid.UUID,
    publisher: RecordingPublisher,
) -> None:
    plugin = await _make_published_plugin(make_plugin, plugin_service, organization_id)
    installed = await installation_service.install(organization_id, plugin.id)
    publisher.events.clear()

    disabled = await installation_service.disable(organization_id, installed.id)

    assert disabled.status == PluginInstallationStatus.DISABLED
    assert disabled.disabled_at is not None
    assert publisher.names == ["PluginDisabled"]
    assert publisher.events[0].payload["installation_id"] == str(installed.id)


async def test_remove_sets_status_and_emits_event(
    installation_service: PluginInstallationService,
    plugin_service: PluginService,
    make_plugin: MakePluginFn,
    organization_id: uuid.UUID,
    publisher: RecordingPublisher,
) -> None:
    plugin = await _make_published_plugin(make_plugin, plugin_service, organization_id)
    installed = await installation_service.install(organization_id, plugin.id)
    publisher.events.clear()

    removed = await installation_service.remove(organization_id, installed.id)

    assert removed.status == PluginInstallationStatus.REMOVED
    assert removed.removed_at is not None
    assert publisher.names == ["PluginRemoved"]
    assert publisher.events[0].payload["installation_id"] == str(installed.id)


# ---- upgrade ------------------------------------------------------------------


async def test_upgrade_happy_path(
    installation_service: PluginInstallationService,
    plugin_service: PluginService,
    make_plugin: MakePluginFn,
    organization_id: uuid.UUID,
    upgrades_repo: PluginUpgradeRepository,
    publisher: RecordingPublisher,
) -> None:
    plugin = await _make_published_plugin(make_plugin, plugin_service, organization_id)
    installed = await installation_service.install(organization_id, plugin.id)
    await _publish_version(plugin_service, organization_id, plugin.id, version_number="1.1.0")
    publisher.events.clear()

    upgraded = await installation_service.upgrade(
        organization_id,
        installed.id,
        to_version_number="1.1.0",
        strategy=UpgradeStrategy.MANUAL,
        initiated_by="tester",
    )

    assert upgraded.installed_version_number == "1.1.0"
    assert upgraded.status == PluginInstallationStatus.ACTIVE

    history = await upgrades_repo.list_for_installation(installed.id)
    assert len(history) == 1
    assert history[0].from_version_number == "1.0.0"
    assert history[0].to_version_number == "1.1.0"
    assert history[0].status == UpgradeStatus.COMPLETED
    assert history[0].completed_at is not None

    assert publisher.names == ["PluginUpgraded"]
    event = publisher.events[0]
    assert event.payload["installation_id"] == str(installed.id)
    assert event.payload["from_version_number"] == "1.0.0"
    assert event.payload["to_version_number"] == "1.1.0"


async def test_upgrade_to_non_newer_version_raises(
    installation_service: PluginInstallationService,
    plugin_service: PluginService,
    make_plugin: MakePluginFn,
    organization_id: uuid.UUID,
) -> None:
    plugin = await _make_published_plugin(make_plugin, plugin_service, organization_id)
    installed = await installation_service.install(organization_id, plugin.id)

    with pytest.raises(ValidationError):
        await installation_service.upgrade(organization_id, installed.id, to_version_number="1.0.0")


async def test_upgrade_to_never_published_version_raises(
    installation_service: PluginInstallationService,
    plugin_service: PluginService,
    make_plugin: MakePluginFn,
    organization_id: uuid.UUID,
) -> None:
    plugin = await _make_published_plugin(make_plugin, plugin_service, organization_id)
    installed = await installation_service.install(organization_id, plugin.id)

    with pytest.raises(ValidationError):
        await installation_service.upgrade(organization_id, installed.id, to_version_number="9.9.9")


# ---- rollback ------------------------------------------------------------------


async def test_rollback_happy_path(
    installation_service: PluginInstallationService,
    plugin_service: PluginService,
    make_plugin: MakePluginFn,
    organization_id: uuid.UUID,
    rollbacks_repo: PluginRollbackRepository,
    publisher: RecordingPublisher,
) -> None:
    plugin = await _make_published_plugin(make_plugin, plugin_service, organization_id)
    installed = await installation_service.install(organization_id, plugin.id)
    await _publish_version(plugin_service, organization_id, plugin.id, version_number="1.1.0")
    await installation_service.upgrade(organization_id, installed.id, to_version_number="1.1.0")
    publisher.events.clear()

    rolled_back = await installation_service.rollback(
        organization_id,
        installed.id,
        to_version_number="1.0.0",
        reason="regression",
        initiated_by="tester",
    )

    assert rolled_back.installed_version_number == "1.0.0"
    assert rolled_back.status == PluginInstallationStatus.ACTIVE

    history = await rollbacks_repo.list_for_installation(installed.id)
    assert len(history) == 1
    assert history[0].from_version_number == "1.1.0"
    assert history[0].to_version_number == "1.0.0"
    assert history[0].status == RollbackStatus.COMPLETED
    assert history[0].reason == "regression"
    assert history[0].completed_at is not None

    assert publisher.names == ["PluginRolledBack"]
    event = publisher.events[0]
    assert event.payload["installation_id"] == str(installed.id)
    assert event.payload["to_version_number"] == "1.0.0"


async def test_rollback_to_non_older_version_raises(
    installation_service: PluginInstallationService,
    plugin_service: PluginService,
    make_plugin: MakePluginFn,
    organization_id: uuid.UUID,
) -> None:
    plugin = await _make_published_plugin(make_plugin, plugin_service, organization_id)
    installed = await installation_service.install(organization_id, plugin.id)
    await _publish_version(plugin_service, organization_id, plugin.id, version_number="1.1.0")
    await installation_service.upgrade(organization_id, installed.id, to_version_number="1.1.0")

    with pytest.raises(ValidationError):
        await installation_service.rollback(organization_id, installed.id, to_version_number="1.1.0")


async def test_rollback_to_never_installed_version_raises(
    installation_service: PluginInstallationService,
    plugin_service: PluginService,
    make_plugin: MakePluginFn,
    organization_id: uuid.UUID,
) -> None:
    plugin = await _make_published_plugin(make_plugin, plugin_service, organization_id)
    installed = await installation_service.install(organization_id, plugin.id)

    # No upgrade history exists at all yet, so no older version was ever
    # actually installed on this instance -- even though "0.5.0" really is
    # older than the current "1.0.0".
    with pytest.raises(ValidationError):
        await installation_service.rollback(organization_id, installed.id, to_version_number="0.5.0")
