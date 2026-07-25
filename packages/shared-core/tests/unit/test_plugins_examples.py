"""Tests for the real sample plugin under examples/hello_plugin.py, proving
the full framework works end-to-end against an actual (not mocked) plugin.
"""

from __future__ import annotations

from pathlib import Path

import shared_core.plugins.examples as examples_package
from shared_core.plugins.examples.hello_plugin import HelloPlugin
from shared_core.plugins.hooks import BEFORE_STARTUP
from shared_core.plugins.lifecycle import PluginState
from shared_core.plugins.manager import PluginManager
from shared_core.plugins.manifest import PluginManifest, parse_manifest_yaml


def _load_manifest() -> PluginManifest:
    examples_dir = Path(examples_package.__file__).parent
    text = (examples_dir / "hello_plugin.manifest.yaml").read_text(encoding="utf-8")
    return parse_manifest_yaml(text)


def test_hello_plugin_manifest_parses_and_matches_the_class() -> None:
    manifest = _load_manifest()

    assert manifest.metadata.plugin_id == "hello-plugin"
    assert manifest.entry_point == "shared_core.plugins.examples.hello_plugin:HelloPlugin"


async def test_hello_plugin_runs_end_to_end_through_the_manager() -> None:
    manifest = _load_manifest()
    manager = PluginManager()

    await manager.install(manifest)
    manager.enable("hello-plugin")
    record = await manager.initialize("hello-plugin")

    instance = record.instance
    assert isinstance(instance, HelloPlugin)

    record = await manager.start("hello-plugin")
    assert record.lifecycle.state == PluginState.STARTED

    # The plugin wired its own @hook-tagged callback into the shared registry.
    assert len(manager.hooks.registered_hooks(BEFORE_STARTUP)) == 1

    # And its own @extension-tagged contribution too.
    contributions = manager.extensions.point("ui.menus").list_contributions()
    assert [c.plugin_id for c in contributions] == ["hello-plugin"]
    assert contributions[0].value == {"label": "Hello Plugin", "route": "/plugins/hello"}

    await manager.stop("hello-plugin")
    manager.disable("hello-plugin")
    manager.uninstall("hello-plugin")

    assert manager.hooks.registered_hooks(BEFORE_STARTUP) == []
    assert manager.extensions.point("ui.menus").list_contributions() == []
