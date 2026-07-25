"""Plugin unloader.

Per docs/029_Enterprise_Plugin_Framework.md.txt "PLUGIN LOADER": Unload.
The inverse of :meth:`shared_core.plugins.loader.PluginLoader.load`:
drops a plugin's imported module reference (both this loader's own
tracking and Python's ``sys.modules`` cache) so a later ``load()``/
``reload()`` re-imports it fresh, rather than reusing stale bytecode.
Calling a plugin instance's own
:meth:`~shared_core.plugins.sdk.base.Plugin.on_stop` first is the
lifecycle orchestrator's job (:mod:`shared_core.plugins.manager`), not
this module's -- unloading and stopping are separate concerns.
"""

from __future__ import annotations

import sys

from shared_core.plugins.loader import PluginLoader, parse_entry_point
from shared_core.plugins.manifest import PluginManifest


class PluginUnloader:
    """Drops a plugin's imported module reference ("Unload")."""

    def __init__(self, loader: PluginLoader) -> None:
        self._loader = loader

    def unload(self, manifest: PluginManifest) -> None:
        """Drop *manifest*'s imported module from ``sys.modules`` and this loader's cache."""
        module_path, _ = parse_entry_point(manifest.entry_point)
        sys.modules.pop(module_path, None)
        self._loader.forget(manifest.metadata.plugin_id)


__all__ = ["PluginUnloader"]
