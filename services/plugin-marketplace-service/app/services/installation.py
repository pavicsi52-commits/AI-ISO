"""Plugin installation lifecycle: install, activate, configure, upgrade,
rollback, disable, remove (docs/059 "INSTALLATION MANAGEMENT").
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from shared_core.exceptions.validation import ValidationError
from shared_core.plugins.versioning import is_downgrade, is_upgrade

from app.events.plugin_events import (
    SOURCE_SERVICE,
    PluginActivatedEvent,
    PluginDisabledEvent,
    PluginInstalledEvent,
    PluginRemovedEvent,
    PluginRolledBackEvent,
    PluginUpgradedEvent,
)
from app.models.enums import (
    InstallationTrigger,
    PluginInstallationStatus,
    RollbackStatus,
    UpgradeStatus,
    UpgradeStrategy,
)
from app.models.installation import PluginInstallation
from app.models.upgrade import PluginRollback, PluginUpgrade
from app.repositories.dependency import PluginDependencyRepository
from app.repositories.installation import PluginInstallationRepository
from app.repositories.plugin import PluginRepository, PluginVersionRepository
from app.repositories.upgrade import PluginRollbackRepository, PluginUpgradeRepository
from app.types import EventPublisher


class PluginInstallationService:
    """Moves one organization's own installed plugin instance through its
    own install/activate/configure/upgrade/rollback/disable/remove lifecycle.
    """

    def __init__(
        self,
        installations: PluginInstallationRepository,
        plugins: PluginRepository,
        versions: PluginVersionRepository,
        dependencies: PluginDependencyRepository,
        upgrades: PluginUpgradeRepository,
        rollbacks: PluginRollbackRepository,
        *,
        publish_event: EventPublisher | None = None,
    ) -> None:
        self._installations = installations
        self._plugins = plugins
        self._versions = versions
        self._dependencies = dependencies
        self._upgrades = upgrades
        self._rollbacks = rollbacks
        self._publish = publish_event

    async def install(
        self,
        organization_id: UUID,
        plugin_id: UUID,
        *,
        trigger: InstallationTrigger = InstallationTrigger.ONLINE,
        installed_by: str | None = None,
    ) -> PluginInstallation:
        """Install a published plugin into this organization.

        Raises:
            ValidationError: If the plugin has no published version, is
                already installed in this organization, or a required
                dependency is not itself installed.
        """
        plugin = await self._plugins.require_in_org(organization_id, plugin_id)
        if plugin.current_version_number is None:
            raise ValidationError(f"Plugin {plugin_id} has no published version to install.")
        if await self._installations.get_for_plugin(organization_id, plugin_id) is not None:
            raise ValidationError(f"Plugin {plugin_id} is already installed in this organization.")

        for edge in await self._dependencies.list_for_plugin(plugin_id):
            if edge.optional:
                continue
            dependency_installed = await self._installations.get_for_plugin(
                organization_id, edge.depends_on_plugin_id
            )
            if dependency_installed is None:
                raise ValidationError(
                    f"Required dependency {edge.depends_on_plugin_id} is not installed."
                )

        installation = await self._installations.create(
            PluginInstallation(
                organization_id=organization_id,
                plugin_id=plugin_id,
                installed_version_number=plugin.current_version_number,
                status=PluginInstallationStatus.INSTALLED,
                trigger=trigger,
                installed_by=installed_by,
                installed_at=datetime.now(UTC),
            )
        )
        await self._publish_event(
            PluginInstalledEvent(
                source_service=SOURCE_SERVICE,
                organization_id=organization_id,
                payload={
                    "installation_id": str(installation.id),
                    "plugin_id": str(plugin_id),
                    "version_number": installation.installed_version_number,
                },
            )
        )
        return installation

    async def get(self, organization_id: UUID, installation_id: UUID) -> PluginInstallation:
        """One installation.

        Raises:
            NotFoundError: If it does not exist here.
        """
        return await self._installations.require_in_org(organization_id, installation_id)

    async def list_for_org(
        self,
        organization_id: UUID,
        *,
        status: PluginInstallationStatus | None = None,
        limit: int = 200,
        offset: int = 0,
    ) -> list[PluginInstallation]:
        """This organization's own installations, newest first."""
        return await self._installations.list_for_org(
            organization_id, status=status, limit=limit, offset=offset
        )

    async def configure(
        self, organization_id: UUID, installation_id: UUID, *, configuration: dict[str, Any]
    ) -> PluginInstallation:
        """Update an installation's own configuration.

        Only advances ``status`` to ``CONFIGURED`` from the pre-activation
        states (``INSTALLING``/``INSTALLED``). Reconfiguring an
        already-``ACTIVE`` installation must not silently knock it out of
        the health-probe sweep's own ``list_all_active`` scope, which
        filters on ``status`` alone -- this service has no separate
        ``enabled`` boolean column the way ``Connector`` does, where a
        similar unconditional ``status = CONFIGURED`` is safe because
        ``list_all_enabled`` filters on that independent flag instead.
        """
        installation = await self.get(organization_id, installation_id)
        installation.configuration = dict(configuration)
        if installation.status in (
            PluginInstallationStatus.INSTALLING,
            PluginInstallationStatus.INSTALLED,
        ):
            installation.status = PluginInstallationStatus.CONFIGURED
        return await self._installations.update(installation)

    async def activate(self, organization_id: UUID, installation_id: UUID) -> PluginInstallation:
        """Activate a configured installation -- it becomes eligible for
        sandboxed execution and health probing.
        """
        installation = await self.get(organization_id, installation_id)
        installation.status = PluginInstallationStatus.ACTIVE
        installation.activated_at = datetime.now(UTC)
        installation = await self._installations.update(installation)
        await self._publish_event(
            PluginActivatedEvent(
                source_service=SOURCE_SERVICE,
                organization_id=organization_id,
                payload={"installation_id": str(installation_id)},
            )
        )
        return installation

    async def disable(self, organization_id: UUID, installation_id: UUID) -> PluginInstallation:
        """Disable an installation."""
        installation = await self.get(organization_id, installation_id)
        installation.status = PluginInstallationStatus.DISABLED
        installation.disabled_at = datetime.now(UTC)
        installation = await self._installations.update(installation)
        await self._publish_event(
            PluginDisabledEvent(
                source_service=SOURCE_SERVICE,
                organization_id=organization_id,
                payload={"installation_id": str(installation_id)},
            )
        )
        return installation

    async def remove(self, organization_id: UUID, installation_id: UUID) -> PluginInstallation:
        """Remove an installation -- the terminal lifecycle stage."""
        installation = await self.get(organization_id, installation_id)
        installation.status = PluginInstallationStatus.REMOVED
        installation.removed_at = datetime.now(UTC)
        installation = await self._installations.update(installation)
        await self._publish_event(
            PluginRemovedEvent(
                source_service=SOURCE_SERVICE,
                organization_id=organization_id,
                payload={"installation_id": str(installation_id)},
            )
        )
        return installation

    async def upgrade(
        self,
        organization_id: UUID,
        installation_id: UUID,
        *,
        to_version_number: str,
        strategy: UpgradeStrategy = UpgradeStrategy.MANUAL,
        initiated_by: str | None = None,
    ) -> PluginInstallation:
        """Upgrade an installation to a newer, already-published version.

        Raises:
            ValidationError: If *to_version_number* is not newer than the
                installation's own current version, or was never published.
        """
        installation = await self.get(organization_id, installation_id)
        if not is_upgrade(installation.installed_version_number, to_version_number):
            raise ValidationError(
                f"{to_version_number!r} is not newer than the current version "
                f"{installation.installed_version_number!r}."
            )
        target = await self._versions.get_by_version_number(
            installation.plugin_id, to_version_number
        )
        if target is None:
            raise ValidationError(f"Version {to_version_number!r} was never published.")

        record = await self._upgrades.create(
            PluginUpgrade(
                organization_id=organization_id,
                plugin_installation_id=installation_id,
                from_version_number=installation.installed_version_number,
                to_version_number=to_version_number,
                strategy=strategy,
                status=UpgradeStatus.IN_PROGRESS,
                started_at=datetime.now(UTC),
                initiated_by=initiated_by,
            )
        )
        installation.status = PluginInstallationStatus.UPGRADING
        await self._installations.update(installation)

        installation.installed_version_number = to_version_number
        installation.status = PluginInstallationStatus.ACTIVE
        installation = await self._installations.update(installation)

        record.status = UpgradeStatus.COMPLETED
        record.completed_at = datetime.now(UTC)
        await self._upgrades.update(record)

        await self._publish_event(
            PluginUpgradedEvent(
                source_service=SOURCE_SERVICE,
                organization_id=organization_id,
                payload={
                    "installation_id": str(installation_id),
                    "from_version_number": record.from_version_number,
                    "to_version_number": to_version_number,
                },
            )
        )
        return installation

    async def rollback(
        self,
        organization_id: UUID,
        installation_id: UUID,
        *,
        to_version_number: str,
        reason: str | None = None,
        initiated_by: str | None = None,
    ) -> PluginInstallation:
        """Roll an installation back to an older, previously-installed version.

        Raises:
            ValidationError: If *to_version_number* is not older than the
                installation's own current version, or was never
                previously installed on this instance.
        """
        installation = await self.get(organization_id, installation_id)
        if not is_downgrade(installation.installed_version_number, to_version_number):
            raise ValidationError(
                f"{to_version_number!r} is not older than the current version "
                f"{installation.installed_version_number!r}."
            )
        history = await self._upgrades.list_for_installation(installation_id)
        ever_installed = to_version_number in {record.from_version_number for record in history} | {
            record.to_version_number for record in history
        }
        if not ever_installed:
            raise ValidationError(
                f"Version {to_version_number!r} was never installed on this instance."
            )

        record = await self._rollbacks.create(
            PluginRollback(
                organization_id=organization_id,
                plugin_installation_id=installation_id,
                from_version_number=installation.installed_version_number,
                to_version_number=to_version_number,
                status=RollbackStatus.IN_PROGRESS,
                reason=reason,
                started_at=datetime.now(UTC),
                initiated_by=initiated_by,
            )
        )
        installation.status = PluginInstallationStatus.ROLLING_BACK
        await self._installations.update(installation)

        installation.installed_version_number = to_version_number
        installation.status = PluginInstallationStatus.ACTIVE
        installation = await self._installations.update(installation)

        record.status = RollbackStatus.COMPLETED
        record.completed_at = datetime.now(UTC)
        await self._rollbacks.update(record)

        await self._publish_event(
            PluginRolledBackEvent(
                source_service=SOURCE_SERVICE,
                organization_id=organization_id,
                payload={
                    "installation_id": str(installation_id),
                    "to_version_number": to_version_number,
                },
            )
        )
        return installation

    async def _publish_event(self, event: Any) -> None:
        if self._publish is not None:
            await self._publish(event)


__all__ = ["PluginInstallationService"]
