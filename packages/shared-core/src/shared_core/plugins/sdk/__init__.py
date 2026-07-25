"""Plugin SDK.

The public surface a plugin author imports against: the
:class:`~shared_core.plugins.sdk.base.Plugin` contract and the
:class:`~shared_core.plugins.sdk.context.PluginContext` handed to it.
"""

from __future__ import annotations

from shared_core.plugins.sdk.base import Plugin
from shared_core.plugins.sdk.context import PluginContext

__all__ = ["Plugin", "PluginContext"]
