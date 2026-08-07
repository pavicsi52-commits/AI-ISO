"""Plugin registration and lifecycle management (docs/059 "PLUGIN LIFECYCLE")."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from shared_core.exceptions.validation import ValidationError
from shared_core.plugins.versioning import is_upgrade, parse_version

from app.events.plugin_events import SOURCE_SERVICE, PluginPublishedEvent, PluginRegisteredEvent
from app.manifests.engine import validate_manifest
from app.models.enums import (
    ManifestValidationStatus,
    PluginCategory,
    PluginLifecycleStatus,
    PluginType,
)
from app.models.manifest import PluginManifestEntry
from app.models.plugin import Plugin, PluginVersion
from app.repositories.manifest import PluginManifestRepository
from app.repositories.plugin import PluginRepository, PluginVersionRepository
from app.types import EventPublisher


class PluginService:
    """Registers a plugin and moves it through Registration -> Validation ->
    Publishing -> Approval.
    """

    def __init__(
        self,
        plugins: PluginRepository,
        versions: PluginVersionRepository,
        manifests: PluginManifestRepository,
        *,
        publish_event: EventPublisher | None = None,
    ) -> None:
        self._plugins = plugins
        self._versions = versions
        self._manifests = manifests
        self._publish = publish_event

    async def register(
        self,
        organization_id: UUID,
        *,
        slug: str,
        name: str,
        category: PluginCategory,
        plugin_type: PluginType,
        publisher_id: UUID | None = None,
        description: str | None = None,
        homepage_url: str | None = None,
        license_name: str | None = None,
        tags: list[str] | None = None,
        owner_id: str | None = None,
    ) -> Plugin:
        """Register a new plugin definition -- the lifecycle's own first stage.

        Raises:
            ValidationError: If *slug* is already registered in this organization.
        """
        if await self._plugins.get_by_slug(organization_id, slug) is not None:
            raise ValidationError(f"A plugin with slug {slug!r} is already registered.")
        plugin = await self._plugins.create(
            Plugin(
                organization_id=organization_id,
                slug=slug,
                name=name,
                category=category,
                plugin_type=plugin_type,
                publisher_id=publisher_id,
                description=description,
                homepage_url=homepage_url,
                license=license_name,
                tags=list(tags or []),
                owner_id=owner_id,
                status=PluginLifecycleStatus.REGISTERED,
            )
        )
        await self._publish_event(
            PluginRegisteredEvent(
                source_service=SOURCE_SERVICE,
                organization_id=organization_id,
                payload={"plugin_id": str(plugin.id), "slug": slug},
            )
        )
        return plugin

    async def get(self, organization_id: UUID, plugin_id: UUID) -> Plugin:
        """One plugin.

        Raises:
            NotFoundError: If it does not exist here.
        """
        return await self._plugins.require_in_org(organization_id, plugin_id)

    async def list_for_org(
        self,
        organization_id: UUID,
        *,
        category: PluginCategory | None = None,
        status: PluginLifecycleStatus | None = None,
        limit: int = 200,
        offset: int = 0,
    ) -> list[Plugin]:
        """Plugins owned by this organization, newest first."""
        return await self._plugins.list_for_org(
            organization_id,
            category=str(category) if category else None,
            status=status,
            limit=limit,
            offset=offset,
        )

    async def submit_manifest(
        self,
        organization_id: UUID,
        plugin_id: UUID,
        *,
        version_number: str,
        manifest: dict[str, Any],
        changelog: str | None = None,
        released_by: str | None = None,
    ) -> tuple[PluginVersion, PluginManifestEntry]:
        """Submit a new version with its own manifest -- validates the
        manifest and moves the plugin into ``VALIDATED`` or leaves the
        manifest ``INVALID`` for the submitter to fix.

        Raises:
            ValidationError: If *version_number* is not newer than the
                plugin's own current version, or a version with this
                number already exists.
        """
        plugin = await self.get(organization_id, plugin_id)
        if plugin.current_version_number and not is_upgrade(
            plugin.current_version_number, version_number
        ):
            raise ValidationError(
                f"{version_number!r} is not newer than the current version "
                f"{plugin.current_version_number!r}."
            )
        parse_version(version_number)
        if await self._versions.get_by_version_number(plugin_id, version_number) is not None:
            raise ValidationError(f"Version {version_number!r} already exists for this plugin.")

        result = validate_manifest(manifest)
        version = await self._versions.create(
            PluginVersion(
                organization_id=organization_id,
                plugin_id=plugin_id,
                version_number=version_number,
                changelog=changelog,
                entry_points=list(manifest.get("entry_points", [])),
                configuration_schema=dict(manifest.get("configuration_schema", {})),
                api_requirements=list(manifest.get("api_requirements", [])),
                health_checks=list(manifest.get("health_checks", [])),
                is_current=False,
                released_at=datetime.now(UTC),
                released_by=released_by,
            )
        )
        manifest_entry = await self._manifests.create(
            PluginManifestEntry(
                organization_id=organization_id,
                plugin_id=plugin_id,
                plugin_version_id=version.id,
                raw_content=dict(manifest),
                publisher_name=manifest.get("publisher"),
                checksum=result.checksum,
                validation_status=(
                    ManifestValidationStatus.VALID
                    if result.valid
                    else ManifestValidationStatus.INVALID
                ),
                validation_errors=list(result.errors),
                validated_at=datetime.now(UTC),
            )
        )
        if result.valid:
            plugin.status = PluginLifecycleStatus.VALIDATED
            await self._plugins.update(plugin)
        return version, manifest_entry

    async def publish(
        self, organization_id: UUID, plugin_id: UUID, *, version_number: str
    ) -> Plugin:
        """Publish a validated version -- moves the plugin into ``PUBLISHED``
        and that version into ``is_current``.

        Raises:
            ValidationError: If the version was never submitted, or its
                manifest never passed validation.
        """
        plugin = await self.get(organization_id, plugin_id)
        version = await self._versions.get_by_version_number(plugin_id, version_number)
        if version is None:
            raise ValidationError(f"Version {version_number!r} was never submitted.")
        manifest_entry = await self._manifests.get_for_version(version.id)
        if (
            manifest_entry is None
            or manifest_entry.validation_status != ManifestValidationStatus.VALID
        ):
            raise ValidationError(f"Version {version_number!r} does not have a validated manifest.")

        current = await self._versions.get_current(plugin_id)
        if current is not None and current.id != version.id:
            current.is_current = False
            await self._versions.update(current)
        version.is_current = True
        await self._versions.update(version)

        plugin.status = PluginLifecycleStatus.PUBLISHED
        plugin.current_version_number = version_number
        plugin = await self._plugins.update(plugin)

        await self._publish_event(
            PluginPublishedEvent(
                source_service=SOURCE_SERVICE,
                organization_id=organization_id,
                payload={"plugin_id": str(plugin_id), "version_number": version_number},
            )
        )
        return plugin

    async def submit_for_approval(self, organization_id: UUID, plugin_id: UUID) -> Plugin:
        """Move a published plugin into ``PENDING_APPROVAL``."""
        plugin = await self.get(organization_id, plugin_id)
        plugin.status = PluginLifecycleStatus.PENDING_APPROVAL
        return await self._plugins.update(plugin)

    async def approve(self, organization_id: UUID, plugin_id: UUID) -> Plugin:
        """Approve a pending plugin."""
        plugin = await self.get(organization_id, plugin_id)
        plugin.status = PluginLifecycleStatus.APPROVED
        return await self._plugins.update(plugin)

    async def reject(self, organization_id: UUID, plugin_id: UUID) -> Plugin:
        """Reject a pending plugin."""
        plugin = await self.get(organization_id, plugin_id)
        plugin.status = PluginLifecycleStatus.REJECTED
        return await self._plugins.update(plugin)

    async def deprecate(self, organization_id: UUID, plugin_id: UUID) -> Plugin:
        """Mark a plugin deprecated -- still installable, flagged for eventual removal."""
        plugin = await self.get(organization_id, plugin_id)
        plugin.status = PluginLifecycleStatus.DEPRECATED
        return await self._plugins.update(plugin)

    async def archive(self, organization_id: UUID, plugin_id: UUID) -> Plugin:
        """Archive a plugin -- the terminal lifecycle stage."""
        plugin = await self.get(organization_id, plugin_id)
        plugin.status = PluginLifecycleStatus.ARCHIVED
        return await self._plugins.update(plugin)

    async def list_versions(self, organization_id: UUID, plugin_id: UUID) -> list[PluginVersion]:
        """One plugin's own version history, newest first.

        Raises:
            NotFoundError: If the plugin does not exist here.
        """
        plugin = await self.get(organization_id, plugin_id)
        return await self._versions.list_for_plugin(plugin.id)

    async def _publish_event(self, event: Any) -> None:
        if self._publish is not None:
            await self._publish(event)


__all__ = ["PluginService"]
