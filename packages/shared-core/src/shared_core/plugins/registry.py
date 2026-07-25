"""Plugin registry.

Per docs/029_Enterprise_Plugin_Framework.md.txt "PLUGIN REGISTRY":
Maintain Installed Plugins, Enabled Plugins, Disabled Plugins, Versions,
Dependencies, Compatibility, Status, Health. The in-process,
authoritative store of every plugin this process knows about -- the
same "purely in-process" pattern as
:class:`shared_core.workflow.registry.WorkflowRegistry`/
:class:`shared_core.scheduler.registry.JobRegistry`. Persistence across
restarts is a concern for whatever repository layer wraps this
registry in a running service.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from shared_core.plugins.exceptions import PluginNotFoundError
from shared_core.plugins.lifecycle import PluginLifecycle, PluginState
from shared_core.plugins.manifest import PluginManifest
from shared_core.plugins.sdk.base import Plugin

_ENABLED_STATES = frozenset(
    {PluginState.ENABLED, PluginState.INITIALIZED, PluginState.STARTED, PluginState.PAUSED}
)


@dataclass(slots=True)
class PluginRecord:
    """One installed plugin's manifest plus its lifecycle state machine."""

    manifest: PluginManifest
    lifecycle: PluginLifecycle = field(default_factory=PluginLifecycle)
    instance: Plugin | None = None


class PluginRegistry:
    """The authoritative in-process store of every plugin this process knows about."""

    def __init__(self) -> None:
        self._records: dict[str, PluginRecord] = {}

    def register(self, manifest: PluginManifest) -> PluginRecord:
        """Register *manifest* as a newly-discovered plugin ("Installed Plugins")."""
        record = PluginRecord(manifest=manifest)
        self._records[manifest.metadata.plugin_id] = record
        return record

    def unregister(self, plugin_id: str) -> None:
        """Remove *plugin_id* entirely. A no-op if it isn't registered."""
        self._records.pop(plugin_id, None)

    def get(self, plugin_id: str) -> PluginRecord:
        """Look up a plugin's record by id.

        Raises:
            PluginNotFoundError: If no plugin with *plugin_id* is registered.
        """
        try:
            return self._records[plugin_id]
        except KeyError as exc:
            raise PluginNotFoundError(f"Plugin {plugin_id!r} is not registered.") from exc

    def has(self, plugin_id: str) -> bool:
        """Whether *plugin_id* is currently registered."""
        return plugin_id in self._records

    def list_plugins(self) -> list[PluginRecord]:
        """Every currently registered plugin ("Installed Plugins")."""
        return list(self._records.values())

    def list_by_state(self, state: PluginState) -> list[PluginRecord]:
        """Every registered plugin currently in *state* ("Status")."""
        return [record for record in self._records.values() if record.lifecycle.state == state]

    def list_enabled(self) -> list[PluginRecord]:
        """Every plugin currently enabled or further along ("Enabled Plugins")."""
        return [
            record for record in self._records.values() if record.lifecycle.state in _ENABLED_STATES
        ]

    def list_disabled(self) -> list[PluginRecord]:
        """Every plugin currently disabled ("Disabled Plugins")."""
        return self.list_by_state(PluginState.DISABLED)

    def version_of(self, plugin_id: str) -> str:
        """The installed version of *plugin_id* ("Versions").

        Raises:
            PluginNotFoundError: If no plugin with *plugin_id* is registered.
        """
        return self.get(plugin_id).manifest.metadata.version

    def manifests_by_id(self) -> dict[str, PluginManifest]:
        """Every registered plugin's manifest, keyed by id ("Dependencies", "Compatibility").

        Suitable to pass directly to
        :class:`shared_core.plugins.resolver.DependencyResolver`.
        """
        return {plugin_id: record.manifest for plugin_id, record in self._records.items()}


__all__ = ["PluginRecord", "PluginRegistry"]
