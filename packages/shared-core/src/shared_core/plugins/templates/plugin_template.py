"""Starting point for a new AI-IOS plugin.

Copy this file into your own plugin package, rename the class, and
replace each method body with your plugin's own logic. Pair it with a
manifest built from ``manifest_template.yaml`` (same directory) whose
``entry_point`` points at your renamed class.
"""

from __future__ import annotations

from shared_core.plugins.sdk.base import Plugin
from shared_core.plugins.sdk.context import PluginContext


class MyPlugin(Plugin):
    """Rename this class, and give it whatever instance state your plugin needs."""

    def __init__(self) -> None:
        self._context: PluginContext | None = None

    async def on_initialize(self, context: PluginContext) -> None:
        """Called once, after installation/enabling, before the plugin starts.

        Store *context* if later methods need it; register any hook
        callbacks into ``context.hooks`` and any extension
        contributions into ``context.extensions`` here.
        """
        self._context = context

    async def on_start(self) -> None:
        """Start this plugin's active behavior."""

    async def on_stop(self) -> None:
        """Stop this plugin's active behavior and release any resources it holds."""

    async def on_pause(self) -> None:
        """Temporarily suspend this plugin. Override only if your plugin needs it."""
        return None

    async def on_resume(self) -> None:
        """Resume a paused plugin. Override only if your plugin needs it."""
        return None


__all__ = ["MyPlugin"]
