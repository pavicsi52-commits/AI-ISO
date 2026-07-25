"""Plugin dependency declaration.

Per docs/029_Enterprise_Plugin_Framework.md.txt "DEPENDENCY MANAGEMENT":
Required Dependencies, Optional Dependencies, Version Constraints. One
declared edge from a plugin to another plugin it needs -- resolving a
whole manifest set's dependencies (missing/incompatible/circular) is
:mod:`shared_core.plugins.resolver`'s job, not this module's.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class PluginDependency:
    """One dependency edge: the owning manifest requires ``depends_on_plugin_id``.

    Lives inside a :class:`~shared_core.plugins.manifest.PluginManifest`'s
    own ``dependencies`` tuple, so the *dependent* plugin's id is
    implicit (whichever manifest holds this entry); only the *target*
    needs naming here.
    """

    depends_on_plugin_id: str
    version_constraint: str = "*"
    optional: bool = False


__all__ = ["PluginDependency"]
