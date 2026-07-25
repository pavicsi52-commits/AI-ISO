"""Enterprise Plugin Framework factory.

Assembles the registry, permissions, loader, hooks, extensions, and
configuration store into one
:class:`~shared_core.plugins.manager.PluginManager` a service builds
exactly once at startup -- mirroring
:func:`shared_core.workflow.factory.create_workflow_framework`
(Prompt 028) and
:func:`shared_core.scheduler.factory.create_scheduler_framework`
(Prompt 026).
"""

from __future__ import annotations

from shared_core.plugins.constants import DEFAULT_SOURCE_SERVICE
from shared_core.plugins.manager import EventHandler, PluginManager


def create_plugin_framework(
    *, on_event: EventHandler | None = None, source_service: str = DEFAULT_SOURCE_SERVICE
) -> PluginManager:
    """Build a fully-wired :class:`PluginManager` with its default sub-components.

    Every sub-component (:class:`~shared_core.plugins.registry.PluginRegistry`,
    :class:`~shared_core.plugins.permissions.PermissionRegistry`,
    :class:`~shared_core.plugins.loader.PluginLoader`,
    :class:`~shared_core.plugins.hooks.HookRegistry`,
    :class:`~shared_core.plugins.extensions.ExtensionRegistry`,
    :class:`~shared_core.plugins.configuration.PluginConfigurationStore`)
    is purely in-process, so no external connection is required to
    build one -- pass a caller-configured instance of any of them
    directly to :class:`PluginManager` instead of this factory when a
    service needs to share one across multiple frameworks.
    """
    return PluginManager(on_event=on_event, source_service=source_service)


__all__ = ["create_plugin_framework"]
