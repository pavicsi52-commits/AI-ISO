"""Plugin loader.

Per docs/029_Enterprise_Plugin_Framework.md.txt "PLUGIN LOADER": Dynamic
Loading, Lazy Loading, Hot Reload, Reload, Dependency Validation,
Integrity Verification. Imports a plugin's declared entry point
(``"module.path:ClassName"``, per "PLUGIN MANIFEST") and instantiates
it. "Dependency Validation"/"Integrity Verification" (signature
checking) are already implemented by
:mod:`shared_core.plugins.resolver`/:mod:`shared_core.plugins.validator`
and run *before* a caller ever calls this module -- this module's own
job is purely the dynamic import/instantiate/hot-reload step.
"""

from __future__ import annotations

import importlib
import sys
from types import ModuleType

from shared_core.plugins.exceptions import PluginLoadError
from shared_core.plugins.manifest import PluginManifest
from shared_core.plugins.sdk.base import Plugin


def parse_entry_point(entry_point: str) -> tuple[str, str]:
    """Split a manifest's ``"module.path:ClassName"`` entry point.

    Raises:
        PluginLoadError: If *entry_point* isn't in ``module:Class`` shape.
    """
    module_path, _, class_name = entry_point.partition(":")
    if not module_path or not class_name:
        raise PluginLoadError(
            f"Entry point {entry_point!r} is not in 'module.path:ClassName' shape."
        )
    return module_path, class_name


class PluginLoader:
    """Dynamically imports and instantiates plugins from their manifest's entry point."""

    def __init__(self) -> None:
        self._modules: dict[str, ModuleType] = {}

    def load_class(self, manifest: PluginManifest) -> type[Plugin]:
        """Import *manifest*'s entry point class ("Dynamic Loading"/"Lazy Loading").

        Raises:
            PluginLoadError: If the module fails to import, the class
                doesn't exist, or it isn't a :class:`Plugin` subclass.
        """
        module_path, class_name = parse_entry_point(manifest.entry_point)
        try:
            module = importlib.import_module(module_path)
        except ImportError as exc:
            raise PluginLoadError(
                f"Plugin {manifest.metadata.plugin_id!r}'s module {module_path!r} "
                f"could not be imported: {exc}"
            ) from exc
        self._modules[manifest.metadata.plugin_id] = module
        try:
            plugin_class = getattr(module, class_name)
        except AttributeError as exc:
            raise PluginLoadError(
                f"Plugin {manifest.metadata.plugin_id!r}'s entry point class "
                f"{class_name!r} was not found in {module_path!r}."
            ) from exc
        if not (isinstance(plugin_class, type) and issubclass(plugin_class, Plugin)):
            raise PluginLoadError(
                f"Plugin {manifest.metadata.plugin_id!r}'s entry point "
                f"{manifest.entry_point!r} does not implement the Plugin SDK contract."
            )
        return plugin_class

    def load(self, manifest: PluginManifest) -> Plugin:
        """Import and instantiate *manifest*'s entry point class.

        Raises:
            PluginLoadError: If the class can't be imported/found, or instantiating it raises.
        """
        plugin_class = self.load_class(manifest)
        try:
            return plugin_class()
        except Exception as exc:
            raise PluginLoadError(
                f"Plugin {manifest.metadata.plugin_id!r} failed to instantiate: {exc}"
            ) from exc

    def reload(self, manifest: PluginManifest) -> Plugin:
        """Re-import *manifest*'s module and re-instantiate it ("Hot Reload"/"Reload")."""
        module_path, _ = parse_entry_point(manifest.entry_point)
        module = self._modules.get(manifest.metadata.plugin_id) or sys.modules.get(module_path)
        if module is not None:
            try:
                importlib.reload(module)
            except ImportError as exc:
                raise PluginLoadError(
                    f"Plugin {manifest.metadata.plugin_id!r}'s module {module_path!r} "
                    f"could not be reloaded: {exc}"
                ) from exc
        return self.load(manifest)

    def is_loaded(self, plugin_id: str) -> bool:
        """Whether *plugin_id*'s module has been imported by this loader."""
        return plugin_id in self._modules

    def forget(self, plugin_id: str) -> None:
        """Drop this loader's own reference to *plugin_id*'s module. A no-op if untracked."""
        self._modules.pop(plugin_id, None)


__all__ = ["PluginLoader", "parse_entry_point"]
