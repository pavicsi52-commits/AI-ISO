"""A complete, runnable sample plugin ("Generate a sample plugin for testing").

:mod:`shared_core.plugins.examples.hello_plugin` is a real plugin --
loadable via :class:`~shared_core.plugins.loader.PluginLoader` and
runnable end-to-end through :class:`~shared_core.plugins.manager.PluginManager`
exactly like any third-party plugin would be -- demonstrating the
minimum a plugin author needs: a manifest, a
:class:`~shared_core.plugins.sdk.base.Plugin` subclass, a hook
registration, and an extension contribution.
"""

from __future__ import annotations
