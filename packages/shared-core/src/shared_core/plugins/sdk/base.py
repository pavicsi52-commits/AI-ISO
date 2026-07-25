"""Plugin SDK: base contract.

Per docs/029_Enterprise_Plugin_Framework.md.txt "PLUGIN SDK". Every
plugin's entry point class implements this ABC -- the framework's
loader instantiates it and drives it through the exact same lifecycle
hooks regardless of what the plugin actually does, the same "the SDK
provides the contract, callers provide the behavior" shape as every
other Prompt 021-028 framework's own base class (e.g.
:class:`shared_core.connectors.base.BaseConnector`).
"""

from __future__ import annotations

from abc import ABC, abstractmethod

from shared_core.plugins.sdk.context import PluginContext


class Plugin(ABC):
    """The contract every plugin's entry point class must implement."""

    @abstractmethod
    async def on_initialize(self, context: PluginContext) -> None:
        """Called once, after installation/enabling, before the plugin starts."""

    @abstractmethod
    async def on_start(self) -> None:
        """Called to start the plugin's active behavior."""

    @abstractmethod
    async def on_stop(self) -> None:
        """Called to stop the plugin's active behavior."""

    async def on_pause(self) -> None:
        """Called to temporarily suspend the plugin. Default: no-op."""
        return None

    async def on_resume(self) -> None:
        """Called to resume a paused plugin. Default: no-op."""
        return None


__all__ = ["Plugin"]
