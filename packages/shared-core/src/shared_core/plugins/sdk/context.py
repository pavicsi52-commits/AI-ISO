"""Plugin SDK: execution context.

Per docs/029_Enterprise_Plugin_Framework.md.txt "PLUGIN SDK"/
"EXTENSION POINTS"/"EVENT HOOKS". What the host framework hands a
plugin at :meth:`~shared_core.plugins.sdk.base.Plugin.on_initialize`
time -- its own configuration, a scoped logger, the sandbox it must
consult before touching a restricted resource
(:mod:`shared_core.plugins.permissions`/:mod:`shared_core.plugins.sandbox`),
and the host's shared :class:`~shared_core.plugins.hooks.HookRegistry`/
:class:`~shared_core.plugins.extensions.ExtensionRegistry` -- the
"wire later" half of :mod:`shared_core.plugins.decorators`'s
``@hook``/``@extension`` "mark now, wire later" pattern: a plugin's own
``on_initialize`` registers its ``@hook``-tagged callbacks and
``@extension``-tagged contributions into these directly, the same way
a workflow SDK caller manually registers an ``@node_handler``-tagged
function into its own ``NodeHandlerRegistry``.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from shared_core.logging.logger import AIIOSLogger, get_logger
from shared_core.plugins.extensions import ExtensionRegistry
from shared_core.plugins.hooks import HookRegistry
from shared_core.plugins.permissions import PluginPermission
from shared_core.plugins.sandbox import PluginSandbox


@dataclass(frozen=True, slots=True)
class PluginContext:
    """Everything a plugin needs to interact with the host framework."""

    plugin_id: str
    configuration: dict[str, Any] = field(default_factory=dict)
    sandbox: PluginSandbox | None = None
    hooks: HookRegistry | None = None
    extensions: ExtensionRegistry | None = None
    logger: AIIOSLogger = field(default_factory=lambda: get_logger("shared_core.plugins"))

    def require_permission(self, permission: PluginPermission) -> None:
        """Raise unless this plugin's sandbox grants *permission*.

        A plugin with no sandbox configured (the host trusts it fully,
        e.g. a first-party bundled plugin) always passes.

        Raises:
            SandboxViolationError: If a sandbox is configured and
                doesn't grant *permission*.
        """
        if self.sandbox is not None:
            self.sandbox.check_permission(permission)


__all__ = ["PluginContext"]
