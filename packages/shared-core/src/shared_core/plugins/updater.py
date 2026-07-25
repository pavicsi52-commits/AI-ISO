"""Plugin updater.

Per docs/029_Enterprise_Plugin_Framework.md.txt "PLUGIN LIFECYCLE":
Update. Per "VERSIONING": Upgrade Paths, Downgrade Support, Migration
Hooks. Replaces an installed plugin's manifest with a new version,
re-validating it and running any registered migration hook for the
exact (from_version -> to_version) transition. Only callable while the
plugin is ``INSTALLED``, ``STOPPED``, or ``DISABLED``
(:mod:`shared_core.plugins.lifecycle`'s transition table) -- a running
plugin must be stopped or disabled first, the same "can't update what's
live" rule every other Prompt 021-028 framework's own lifecycle enforces.
"""

from __future__ import annotations

from shared_core.plugins.lifecycle import PluginState
from shared_core.plugins.manifest import PluginManifest
from shared_core.plugins.permissions import PermissionRegistry
from shared_core.plugins.registry import PluginRecord, PluginRegistry
from shared_core.plugins.validator import validate_manifest
from shared_core.plugins.versioning import MigrationRegistry


class PluginUpdater:
    """Updates an installed plugin to a new manifest version ("Update")."""

    def __init__(
        self,
        registry: PluginRegistry,
        permissions: PermissionRegistry,
        migrations: MigrationRegistry | None = None,
    ) -> None:
        self._registry = registry
        self._permissions = permissions
        self._migrations = migrations if migrations is not None else MigrationRegistry()

    async def update(
        self,
        new_manifest: PluginManifest,
        *,
        public_key: str | None = None,
        granted_by: str | None = None,
    ) -> PluginRecord:
        """Replace the installed manifest for *new_manifest*'s plugin id with *new_manifest*.

        Raises:
            PluginNotFoundError: If the plugin isn't currently installed.
            InvalidLifecycleTransitionError: If the plugin isn't
                currently in a state that permits updating.
            VersionIncompatibleError: If *new_manifest* isn't compatible with this framework.
            DependencyResolutionError: If a required dependency is missing/incompatible.
            CircularDependencyError: If updating would create a dependency cycle.
            SignatureVerificationError: If *public_key* is given and the signature doesn't verify.
        """
        plugin_id = new_manifest.metadata.plugin_id
        record = self._registry.get(plugin_id)
        old_version = record.manifest.metadata.version

        others = {
            other_id: other_manifest
            for other_id, other_manifest in self._registry.manifests_by_id().items()
            if other_id != plugin_id
        }
        validate_manifest(new_manifest, installed=others, public_key=public_key)

        record.lifecycle.transition(PluginState.UPDATING)
        await self._migrations.migrate(old_version, new_manifest.metadata.version)
        record.manifest = new_manifest
        record.lifecycle.transition(PluginState.INSTALLED)
        self._permissions.grant(plugin_id, new_manifest.permissions, granted_by=granted_by)
        return record


__all__ = ["PluginUpdater"]
