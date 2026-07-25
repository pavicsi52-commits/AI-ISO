"""Plugin installer.

Per docs/029_Enterprise_Plugin_Framework.md.txt "PLUGIN LIFECYCLE":
Install. Orchestrates the "Validate -> Install" sequence for one
manifest: validates it (:mod:`shared_core.plugins.validator`),
registers it (:mod:`shared_core.plugins.registry`), and records the
permissions actually granted (:mod:`shared_core.plugins.permissions`) --
which may be a subset of what the manifest requested, per docs/029
"Plugins request permissions during installation."
"""

from __future__ import annotations

from shared_core.plugins.exceptions import PluginAlreadyInstalledError
from shared_core.plugins.lifecycle import PluginState
from shared_core.plugins.manifest import PluginManifest
from shared_core.plugins.permissions import PermissionRegistry, PluginPermission
from shared_core.plugins.registry import PluginRecord, PluginRegistry
from shared_core.plugins.validator import validate_manifest


class PluginInstaller:
    """Validates and registers new plugin manifests ("Install")."""

    def __init__(self, registry: PluginRegistry, permissions: PermissionRegistry) -> None:
        self._registry = registry
        self._permissions = permissions

    def install(
        self,
        manifest: PluginManifest,
        *,
        granted_permissions: frozenset[PluginPermission] | None = None,
        public_key: str | None = None,
        granted_by: str | None = None,
    ) -> PluginRecord:
        """Validate and install *manifest*.

        Args:
            manifest: The candidate plugin manifest.
            granted_permissions: The permissions actually granted --
                defaults to every permission *manifest* requested
                (trust it fully); pass an explicit subset to grant less.
            public_key: An RSA public key (PEM) to require a verified
                signature against -- omit to skip signature verification.
            granted_by: Who/what approved this install, for audit.

        Raises:
            PluginAlreadyInstalledError: If *manifest*'s plugin id is already installed.
            VersionIncompatibleError: If *manifest* isn't compatible with this framework.
            DependencyResolutionError: If a required dependency is missing/incompatible.
            CircularDependencyError: If installing *manifest* would create a dependency cycle.
            SignatureVerificationError: If *public_key* is given and the signature doesn't verify.
        """
        plugin_id = manifest.metadata.plugin_id
        if self._registry.has(plugin_id):
            raise PluginAlreadyInstalledError(f"Plugin {plugin_id!r} is already installed.")

        validate_manifest(
            manifest, installed=self._registry.manifests_by_id(), public_key=public_key
        )

        record = self._registry.register(manifest)
        record.lifecycle.transition(PluginState.VALIDATED)
        record.lifecycle.transition(PluginState.INSTALLED)
        self._permissions.grant(
            plugin_id,
            granted_permissions if granted_permissions is not None else manifest.permissions,
            granted_by=granted_by,
        )
        return record


__all__ = ["PluginInstaller"]
