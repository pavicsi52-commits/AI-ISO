"""Plugin manager.

Per docs/029_Enterprise_Plugin_Framework.md.txt "ACCEPTANCE CRITERIA":
the top-level entry point tying every other module in this framework
together -- registration, loading, the full lifecycle (Install ->
Enable -> Initialize -> Start -> Pause/Resume -> Stop -> Disable ->
Update -> Uninstall), permission grants, sandbox policy, extension/hook
cleanup on uninstall, and observability (audit, metrics, events).
Nothing in this module implements plugin behavior itself; it only
wires together modules that already do (``registry``, ``loader``,
``unloader``, ``installer``, ``updater``, ``hooks``, ``extensions``,
``permissions``, ``configuration``, ``audit``, ``metrics``, ``events``).
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable

from shared_core.plugins import audit as plugin_audit
from shared_core.plugins import metrics as plugin_metrics
from shared_core.plugins.configuration import PluginConfigurationStore
from shared_core.plugins.constants import DEFAULT_SOURCE_SERVICE
from shared_core.plugins.events import (
    PluginEvent,
    PluginInstalledEvent,
    PluginStartedEvent,
    PluginStoppedEvent,
    PluginUpdatedEvent,
    build_plugin_event,
)
from shared_core.plugins.exceptions import PluginInitializationError, PluginNotFoundError
from shared_core.plugins.extensions import ExtensionRegistry
from shared_core.plugins.hooks import HookRegistry
from shared_core.plugins.installer import PluginInstaller
from shared_core.plugins.lifecycle import PluginState
from shared_core.plugins.loader import PluginLoader
from shared_core.plugins.manifest import PluginManifest
from shared_core.plugins.permissions import PermissionRegistry, PluginPermission
from shared_core.plugins.registry import PluginRecord, PluginRegistry
from shared_core.plugins.sandbox import PluginSandbox, SandboxPolicy
from shared_core.plugins.sdk.base import Plugin
from shared_core.plugins.sdk.context import PluginContext
from shared_core.plugins.unloader import PluginUnloader
from shared_core.plugins.updater import PluginUpdater
from shared_core.plugins.versioning import MigrationRegistry

EventHandler = Callable[[PluginEvent], Awaitable[None]]


class PluginManager:
    """The top-level entry point: registration, loading, and full lifecycle orchestration."""

    def __init__(
        self,
        *,
        registry: PluginRegistry | None = None,
        permissions: PermissionRegistry | None = None,
        loader: PluginLoader | None = None,
        hooks: HookRegistry | None = None,
        extensions: ExtensionRegistry | None = None,
        configuration: PluginConfigurationStore | None = None,
        migrations: MigrationRegistry | None = None,
        on_event: EventHandler | None = None,
        source_service: str = DEFAULT_SOURCE_SERVICE,
    ) -> None:
        self.registry = registry if registry is not None else PluginRegistry()
        self.permissions = permissions if permissions is not None else PermissionRegistry()
        self.loader = loader if loader is not None else PluginLoader()
        self.unloader = PluginUnloader(self.loader)
        self.hooks = hooks if hooks is not None else HookRegistry()
        self.extensions = extensions if extensions is not None else ExtensionRegistry()
        self.configuration = (
            configuration if configuration is not None else PluginConfigurationStore()
        )
        self._installer = PluginInstaller(self.registry, self.permissions)
        self._updater = PluginUpdater(
            self.registry,
            self.permissions,
            migrations if migrations is not None else MigrationRegistry(),
        )
        self._sandboxes: dict[str, PluginSandbox] = {}
        self._on_event = on_event
        self._source_service = source_service

    def sandbox_for(self, plugin_id: str) -> PluginSandbox | None:
        """The configured sandbox for *plugin_id*, if any."""
        return self._sandboxes.get(plugin_id)

    def set_sandbox_policy(self, plugin_id: str, policy: SandboxPolicy) -> PluginSandbox:
        """Configure (or replace) *plugin_id*'s sandbox policy ("Sandbox Isolation")."""
        sandbox = PluginSandbox(plugin_id, policy)
        self._sandboxes[plugin_id] = sandbox
        return sandbox

    async def install(
        self,
        manifest: PluginManifest,
        *,
        granted_permissions: frozenset[PluginPermission] | None = None,
        public_key: str | None = None,
        actor_id: str | None = None,
    ) -> PluginRecord:
        """Validate, register, and grant permissions for *manifest* ("Install")."""
        record = self._installer.install(
            manifest,
            granted_permissions=granted_permissions,
            public_key=public_key,
            granted_by=actor_id,
        )
        plugin_audit.audit_plugin_installed(manifest.metadata.plugin_id, actor_id=actor_id)
        plugin_metrics.record_installed(len(self.registry.list_plugins()))
        await self._emit(PluginInstalledEvent, manifest.metadata.plugin_id)
        return record

    def enable(self, plugin_id: str, *, actor_id: str | None = None) -> PluginRecord:
        """Transition *plugin_id* to ``ENABLED`` ("Enable").

        Raises:
            PluginNotFoundError: If *plugin_id* is not registered.
            InvalidLifecycleTransitionError: If not currently ``INSTALLED``/``DISABLED``.
        """
        record = self.registry.get(plugin_id)
        record.lifecycle.transition(PluginState.ENABLED)
        plugin_audit.audit_plugin_enabled(plugin_id, actor_id=actor_id)
        return record

    async def initialize(
        self, plugin_id: str, *, configuration: dict[str, object] | None = None
    ) -> PluginRecord:
        """Load *plugin_id*'s entry point and call ``on_initialize()`` ("Initialize").

        Raises:
            PluginNotFoundError: If *plugin_id* is not registered.
            InvalidManifestError: If *configuration* fails the manifest's declared schema.
            PluginLoadError: If the entry point fails to import/instantiate.
            PluginInitializationError: If ``on_initialize()`` raises.
            InvalidLifecycleTransitionError: If not currently ``ENABLED``.
        """
        record = self.registry.get(plugin_id)
        resolved_config = self.configuration.set(
            plugin_id,
            configuration or {},
            schema=record.manifest.configuration_schema or None,
        )
        instance = self.loader.load(record.manifest)
        record.instance = instance
        context = PluginContext(
            plugin_id=plugin_id,
            configuration=resolved_config,
            sandbox=self.sandbox_for(plugin_id),
            hooks=self.hooks,
            extensions=self.extensions,
        )
        try:
            await instance.on_initialize(context)
        except Exception as exc:
            raise PluginInitializationError(
                f"Plugin {plugin_id!r} failed to initialize: {exc}"
            ) from exc
        record.lifecycle.transition(PluginState.INITIALIZED)
        return record

    async def start(self, plugin_id: str) -> PluginRecord:
        """Call *plugin_id*'s ``on_start()`` ("Start").

        Raises:
            PluginNotFoundError: If *plugin_id* is not registered or not yet initialized.
            PluginInitializationError: If ``on_start()`` raises.
            InvalidLifecycleTransitionError: If not currently ``INITIALIZED``.
        """
        record, instance = self._require_instance(plugin_id)
        try:
            with plugin_metrics.measure_execution(plugin_id):
                await instance.on_start()
        except Exception as exc:
            raise PluginInitializationError(f"Plugin {plugin_id!r} failed to start: {exc}") from exc
        record.lifecycle.transition(PluginState.STARTED)
        plugin_metrics.record_running(len(self.registry.list_enabled()))
        await self._emit(PluginStartedEvent, plugin_id)
        return record

    async def pause(self, plugin_id: str) -> PluginRecord:
        """Call *plugin_id*'s ``on_pause()`` ("Pause")."""
        record, instance = self._require_instance(plugin_id)
        await instance.on_pause()
        record.lifecycle.transition(PluginState.PAUSED)
        return record

    async def resume(self, plugin_id: str) -> PluginRecord:
        """Call *plugin_id*'s ``on_resume()`` ("Resume")."""
        record, instance = self._require_instance(plugin_id)
        await instance.on_resume()
        record.lifecycle.transition(PluginState.STARTED)
        return record

    async def stop(self, plugin_id: str) -> PluginRecord:
        """Call *plugin_id*'s ``on_stop()`` ("Stop")."""
        record, instance = self._require_instance(plugin_id)
        await instance.on_stop()
        record.lifecycle.transition(PluginState.STOPPED)
        await self._emit(PluginStoppedEvent, plugin_id)
        return record

    def disable(self, plugin_id: str, *, actor_id: str | None = None) -> PluginRecord:
        """Transition *plugin_id* to ``DISABLED`` ("Disable")."""
        record = self.registry.get(plugin_id)
        record.lifecycle.transition(PluginState.DISABLED)
        plugin_audit.audit_plugin_disabled(plugin_id, actor_id=actor_id)
        return record

    async def update(
        self,
        new_manifest: PluginManifest,
        *,
        public_key: str | None = None,
        actor_id: str | None = None,
    ) -> PluginRecord:
        """Replace an installed plugin's manifest with *new_manifest* ("Update").

        Only callable while the plugin is ``INSTALLED``, ``STOPPED``, or
        ``DISABLED`` -- stop or disable a running plugin first.
        """
        old_version = self.registry.get(new_manifest.metadata.plugin_id).manifest.metadata.version
        record = await self._updater.update(
            new_manifest, public_key=public_key, granted_by=actor_id
        )
        plugin_audit.audit_plugin_updated(
            new_manifest.metadata.plugin_id,
            from_version=old_version,
            to_version=new_manifest.metadata.version,
            actor_id=actor_id,
        )
        await self._emit(PluginUpdatedEvent, new_manifest.metadata.plugin_id)
        return record

    def uninstall(self, plugin_id: str, *, actor_id: str | None = None) -> None:
        """Remove *plugin_id* entirely: module, extensions, hooks, permissions, registry.

        Covers "Uninstall". Only callable while the plugin is ``INSTALLED``, ``ENABLED``,
        ``DISABLED``, ``STOPPED``, or ``FAILED`` -- stop a running
        plugin first.
        """
        record = self.registry.get(plugin_id)
        record.lifecycle.transition(PluginState.UNINSTALLED)
        self.unloader.unload(record.manifest)
        self.extensions.withdraw_all_from(plugin_id)
        self.hooks.unregister_all_from(plugin_id)
        self.permissions.revoke(plugin_id)
        self._sandboxes.pop(plugin_id, None)
        self.registry.unregister(plugin_id)
        plugin_audit.audit_plugin_uninstalled(plugin_id, actor_id=actor_id)

    def _require_instance(self, plugin_id: str) -> tuple[PluginRecord, Plugin]:
        record = self.registry.get(plugin_id)
        if record.instance is None:
            raise PluginNotFoundError(f"Plugin {plugin_id!r} has not been initialized/loaded yet.")
        return record, record.instance

    async def _emit(self, event_cls: type[PluginEvent], plugin_id: str, **extra: object) -> None:
        if self._on_event is None:
            return
        event = build_plugin_event(
            event_cls, source_service=self._source_service, plugin_id=plugin_id, **extra
        )
        await self._on_event(event)


__all__ = ["EventHandler", "PluginManager"]
