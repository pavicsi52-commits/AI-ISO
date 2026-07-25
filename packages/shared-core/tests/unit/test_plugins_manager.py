"""Tests for manager.py, factory.py, and helpers.py."""

from __future__ import annotations

import textwrap
from pathlib import Path

import pytest
from shared_core.plugins.events import PluginEvent
from shared_core.plugins.exceptions import PluginInitializationError, PluginNotFoundError
from shared_core.plugins.factory import create_plugin_framework
from shared_core.plugins.helpers import manifest_summary, plugin_summary
from shared_core.plugins.lifecycle import PluginState
from shared_core.plugins.manager import PluginManager
from shared_core.plugins.manifest import PluginManifest
from shared_core.plugins.metadata import PluginMetadata, PluginType
from shared_core.plugins.permissions import PluginPermission
from shared_core.plugins.sandbox import SandboxPolicy

_TRACKING_PLUGIN_SOURCE = textwrap.dedent("""
    from shared_core.plugins.sdk.base import Plugin


    class TrackingPlugin(Plugin):
        def __init__(self) -> None:
            self.calls: list[str] = []
            self.context = None

        async def on_initialize(self, context) -> None:
            self.context = context
            self.calls.append("initialize")

        async def on_start(self) -> None:
            self.calls.append("start")

        async def on_stop(self) -> None:
            self.calls.append("stop")

        async def on_pause(self) -> None:
            self.calls.append("pause")

        async def on_resume(self) -> None:
            self.calls.append("resume")
    """)


_FAILING_PLUGIN_SOURCE = textwrap.dedent("""
    from shared_core.plugins.sdk.base import Plugin


    class FailingPlugin(Plugin):
        async def on_initialize(self, context) -> None:
            raise RuntimeError("initialize boom")

        async def on_start(self) -> None:
            raise RuntimeError("start boom")

        async def on_stop(self) -> None:
            return None
    """)


def _write_module(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, name: str, source: str) -> None:
    (tmp_path / f"{name}.py").write_text(source)
    monkeypatch.syspath_prepend(str(tmp_path))


def _manifest(
    plugin_id: str = "tracking",
    version: str = "1.0.0",
    entry_point: str = "tracking_plugin:TrackingPlugin",
    permissions: frozenset[PluginPermission] = frozenset(),
) -> PluginManifest:
    return PluginManifest(
        metadata=PluginMetadata(
            plugin_id=plugin_id, name="Tracking", version=version, category=PluginType.AUTOMATION
        ),
        entry_point=entry_point,
        permissions=permissions,
    )


@pytest.fixture
def tracking_manifest(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> PluginManifest:
    _write_module(tmp_path, monkeypatch, "tracking_plugin", _TRACKING_PLUGIN_SOURCE)
    return _manifest()


# --- manager.py: full lifecycle ---


async def test_manager_runs_the_full_plugin_lifecycle(tracking_manifest: PluginManifest) -> None:
    events: list[PluginEvent] = []

    async def on_event(event: PluginEvent) -> None:
        events.append(event)

    manager = PluginManager(on_event=on_event)

    record = await manager.install(tracking_manifest)
    assert record.lifecycle.state == PluginState.INSTALLED

    manager.enable("tracking")
    assert manager.registry.get("tracking").lifecycle.state == PluginState.ENABLED

    record = await manager.initialize("tracking", configuration={"key": "value"})
    assert record.lifecycle.state == PluginState.INITIALIZED
    instance = record.instance
    assert instance is not None
    assert instance.calls == ["initialize"]  # type: ignore[attr-defined]

    record = await manager.start("tracking")
    assert record.lifecycle.state == PluginState.STARTED
    assert instance.calls == ["initialize", "start"]  # type: ignore[attr-defined]

    record = await manager.pause("tracking")
    assert record.lifecycle.state == PluginState.PAUSED

    record = await manager.resume("tracking")
    assert record.lifecycle.state == PluginState.STARTED

    record = await manager.stop("tracking")
    assert record.lifecycle.state == PluginState.STOPPED

    manager.disable("tracking")
    assert manager.registry.get("tracking").lifecycle.state == PluginState.DISABLED

    manager.uninstall("tracking")
    assert manager.registry.has("tracking") is False

    event_names = [event.event_name for event in events]
    assert event_names == ["plugin.installed", "plugin.started", "plugin.stopped"]


async def test_manager_initialize_passes_configuration_into_the_context(
    tracking_manifest: PluginManifest,
) -> None:
    manager = PluginManager()
    await manager.install(tracking_manifest)
    manager.enable("tracking")

    record = await manager.initialize("tracking", configuration={"key": "value"})

    instance = record.instance
    assert instance is not None
    assert instance.context.configuration == {"key": "value"}  # type: ignore[attr-defined]


async def test_manager_start_raises_when_not_yet_initialized(
    tracking_manifest: PluginManifest,
) -> None:
    manager = PluginManager()
    await manager.install(tracking_manifest)
    manager.enable("tracking")

    with pytest.raises(PluginNotFoundError):
        await manager.start("tracking")


async def test_manager_sandbox_policy_is_passed_to_the_plugin_context(
    tracking_manifest: PluginManifest,
) -> None:
    manager = PluginManager()
    await manager.install(tracking_manifest)
    manager.enable("tracking")
    manager.set_sandbox_policy(
        "tracking", SandboxPolicy(allowed_permissions=frozenset({PluginPermission.NETWORK}))
    )

    record = await manager.initialize("tracking")

    instance = record.instance
    assert instance is not None
    assert instance.context.sandbox is manager.sandbox_for("tracking")  # type: ignore[attr-defined]


async def test_manager_uninstall_withdraws_extensions_and_hooks(
    tracking_manifest: PluginManifest,
) -> None:
    manager = PluginManager()
    await manager.install(tracking_manifest)
    manager.extensions.point("ui.menus").contribute("tracking", "main-menu", "value")

    async def callback(*args: object, **kwargs: object) -> None:
        return None

    manager.hooks.register("before_startup", "tracking", callback)

    manager.uninstall("tracking")

    assert manager.extensions.point("ui.menus").list_contributions() == []
    assert manager.hooks.registered_hooks("before_startup") == []
    assert manager.permissions.granted_permissions("tracking") == frozenset()


async def test_manager_update_replaces_the_manifest(tracking_manifest: PluginManifest) -> None:
    manager = PluginManager()
    await manager.install(tracking_manifest)

    new_manifest = _manifest(version="2.0.0")
    record = await manager.update(new_manifest)

    assert record.manifest.metadata.version == "2.0.0"


async def test_manager_initialize_wraps_an_on_initialize_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _write_module(tmp_path, monkeypatch, "failing_plugin", _FAILING_PLUGIN_SOURCE)
    manager = PluginManager()
    await manager.install(_manifest("failing", entry_point="failing_plugin:FailingPlugin"))
    manager.enable("failing")

    with pytest.raises(PluginInitializationError, match="initialize boom"):
        await manager.initialize("failing")


async def test_manager_start_wraps_an_on_start_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _write_module(tmp_path, monkeypatch, "failing_plugin", _FAILING_PLUGIN_SOURCE)
    manager = PluginManager()
    await manager.install(_manifest("failing", entry_point="failing_plugin:FailingPlugin"))
    manager.enable("failing")
    manager.registry.get("failing").instance = manager.loader.load(
        manager.registry.get("failing").manifest
    )
    manager.registry.get("failing").lifecycle.transition(PluginState.INITIALIZED)

    with pytest.raises(PluginInitializationError, match="start boom"):
        await manager.start("failing")


def test_manager_enable_raises_for_unregistered_plugin() -> None:
    manager = PluginManager()

    with pytest.raises(PluginNotFoundError):
        manager.enable("missing")


# --- factory.py ---


async def test_create_plugin_framework_wires_a_working_manager(
    tracking_manifest: PluginManifest,
) -> None:
    manager = create_plugin_framework()

    record = await manager.install(tracking_manifest)

    assert record.lifecycle.state == PluginState.INSTALLED
    assert isinstance(manager, PluginManager)


# --- helpers.py ---


def test_plugin_summary_is_json_serializable(tracking_manifest: PluginManifest) -> None:
    manager = PluginManager()
    record = manager.registry.register(tracking_manifest)

    summary = plugin_summary(record)

    assert summary["plugin_id"] == "tracking"
    assert summary["state"] == "discovered"


def test_manifest_summary_reports_counts(tracking_manifest: PluginManifest) -> None:
    summary = manifest_summary(tracking_manifest)

    assert summary["plugin_id"] == "tracking"
    assert summary["dependency_count"] == 0
    assert summary["permission_count"] == 0
