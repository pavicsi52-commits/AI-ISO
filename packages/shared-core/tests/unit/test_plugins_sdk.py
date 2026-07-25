"""Tests for sdk/base.py and sdk/context.py."""

from __future__ import annotations

import pytest
from shared_core.plugins.exceptions import SandboxViolationError
from shared_core.plugins.permissions import PluginPermission
from shared_core.plugins.sandbox import PluginSandbox, SandboxPolicy
from shared_core.plugins.sdk.base import Plugin
from shared_core.plugins.sdk.context import PluginContext


class _MinimalPlugin(Plugin):
    async def on_initialize(self, context: PluginContext) -> None:
        return None

    async def on_start(self) -> None:
        return None

    async def on_stop(self) -> None:
        return None


async def test_plugin_default_on_pause_and_on_resume_are_no_ops() -> None:
    plugin = _MinimalPlugin()

    await plugin.on_pause()  # doesn't raise
    await plugin.on_resume()  # doesn't raise


def test_plugin_context_require_permission_passes_without_a_sandbox() -> None:
    context = PluginContext(plugin_id="sample")

    context.require_permission(PluginPermission.NETWORK)  # doesn't raise


def test_plugin_context_require_permission_delegates_to_its_sandbox() -> None:
    sandbox = PluginSandbox(
        "sample", SandboxPolicy(allowed_permissions=frozenset({PluginPermission.NETWORK}))
    )
    context = PluginContext(plugin_id="sample", sandbox=sandbox)

    context.require_permission(PluginPermission.NETWORK)  # doesn't raise

    with pytest.raises(SandboxViolationError):
        context.require_permission(PluginPermission.DATABASE)
