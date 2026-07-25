"""A complete, runnable sample plugin.

Demonstrates the minimum a real plugin needs: a
:class:`~shared_core.plugins.sdk.base.Plugin` subclass, a manifest
(``hello_plugin.manifest.yaml``, alongside this file), a
``@hook``-tagged callback registered into the host's shared
:class:`~shared_core.plugins.hooks.HookRegistry` during
``on_initialize``, and an ``@extension``-tagged UI contribution
registered into the host's shared
:class:`~shared_core.plugins.extensions.ExtensionRegistry`. Loadable
via :class:`~shared_core.plugins.loader.PluginLoader` and runnable
end-to-end through :class:`~shared_core.plugins.manager.PluginManager`
exactly like any third-party plugin would be.
"""

from __future__ import annotations

from shared_core.plugins.decorators import extension, get_extension_target, get_hook_name, hook
from shared_core.plugins.hooks import BEFORE_STARTUP
from shared_core.plugins.sdk.base import Plugin
from shared_core.plugins.sdk.context import PluginContext


@hook(BEFORE_STARTUP)
async def _greet(*_args: object, **_kwargs: object) -> None:
    """Log a greeting when the host fires ``BEFORE_STARTUP`` ("Custom Hooks")."""


@extension("ui", "menus")
def _menu_contribution() -> dict[str, str]:
    """This plugin's menu entry ("UI Extensions")."""
    return {"label": "Hello Plugin", "route": "/plugins/hello"}


class HelloPlugin(Plugin):
    """A minimal, real plugin that greets on startup and contributes a menu entry."""

    def __init__(self) -> None:
        self._context: PluginContext | None = None

    async def on_initialize(self, context: PluginContext) -> None:
        """Wire this plugin's ``@hook``/``@extension``-tagged members into the host."""
        self._context = context
        if context.hooks is not None:
            hook_name = get_hook_name(_greet)
            assert hook_name is not None
            context.hooks.register(hook_name, context.plugin_id, _greet)
        if context.extensions is not None:
            target = get_extension_target(_menu_contribution)
            assert target is not None
            namespace, category = target
            context.extensions.point(f"{namespace}.{category}").contribute(
                context.plugin_id, "hello-menu", _menu_contribution()
            )

    async def on_start(self) -> None:
        """Greet via this plugin's context logger."""
        if self._context is not None:
            self._context.logger.info(
                "Hello from HelloPlugin!",
                extra={"extra_fields": {"plugin_id": self._context.plugin_id}},
            )

    async def on_stop(self) -> None:
        """Nothing to release -- this plugin holds no external resources."""


__all__ = ["HelloPlugin"]
