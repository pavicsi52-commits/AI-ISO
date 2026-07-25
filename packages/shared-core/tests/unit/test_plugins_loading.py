"""Tests for loader.py, unloader.py, installer.py, and updater.py."""

from __future__ import annotations

import sys
import textwrap
from pathlib import Path

import pytest
from shared_core.plugins.exceptions import (
    InvalidLifecycleTransitionError,
    PluginAlreadyInstalledError,
    PluginLoadError,
    PluginNotFoundError,
    VersionIncompatibleError,
)
from shared_core.plugins.installer import PluginInstaller
from shared_core.plugins.lifecycle import PluginState
from shared_core.plugins.loader import PluginLoader, parse_entry_point
from shared_core.plugins.manifest import PluginManifest
from shared_core.plugins.metadata import PluginMetadata, PluginType
from shared_core.plugins.permissions import PermissionRegistry, PluginPermission
from shared_core.plugins.registry import PluginRegistry
from shared_core.plugins.sdk.base import Plugin
from shared_core.plugins.unloader import PluginUnloader
from shared_core.plugins.updater import PluginUpdater
from shared_core.plugins.versioning import MigrationRegistry

_VALID_PLUGIN_SOURCE = textwrap.dedent("""
    from shared_core.plugins.sdk.base import Plugin


    class SamplePlugin(Plugin):
        def __init__(self) -> None:
            self.started = False

        async def on_initialize(self, context) -> None:
            self.context = context

        async def on_start(self) -> None:
            self.started = True

        async def on_stop(self) -> None:
            self.started = False
    """)

_NOT_A_PLUGIN_SOURCE = "class NotAPlugin:\n    pass\n"

_ABSTRACT_PLUGIN_SOURCE = textwrap.dedent("""
    from shared_core.plugins.sdk.base import Plugin


    class IncompletePlugin(Plugin):
        async def on_initialize(self, context) -> None:
            return None
    """)


def _write_module(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, name: str, source: str) -> None:
    (tmp_path / f"{name}.py").write_text(source)
    monkeypatch.syspath_prepend(str(tmp_path))


def _manifest(
    plugin_id: str = "sample",
    version: str = "1.0.0",
    entry_point: str = "sample_valid_plugin:SamplePlugin",
    permissions: frozenset[PluginPermission] = frozenset(),
) -> PluginManifest:
    return PluginManifest(
        metadata=PluginMetadata(
            plugin_id=plugin_id, name="Sample", version=version, category=PluginType.AUTOMATION
        ),
        entry_point=entry_point,
        permissions=permissions,
    )


# --- loader.py ---


def test_parse_entry_point_splits_module_and_class() -> None:
    assert parse_entry_point("pkg.mod:ClassName") == ("pkg.mod", "ClassName")


@pytest.mark.parametrize("entry_point", ["no-colon-here", ":ClassName", "pkg.mod:"])
def test_parse_entry_point_raises_for_malformed_input(entry_point: str) -> None:
    with pytest.raises(PluginLoadError):
        parse_entry_point(entry_point)


def test_load_class_imports_a_real_module(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _write_module(tmp_path, monkeypatch, "sample_valid_plugin", _VALID_PLUGIN_SOURCE)
    loader = PluginLoader()
    manifest = _manifest(entry_point="sample_valid_plugin:SamplePlugin")

    plugin_class = loader.load_class(manifest)

    assert issubclass(plugin_class, Plugin)
    assert loader.is_loaded("sample") is True


def test_load_class_raises_for_an_unimportable_module() -> None:
    loader = PluginLoader()
    manifest = _manifest(entry_point="no_such_module_at_all:SamplePlugin")

    with pytest.raises(PluginLoadError):
        loader.load_class(manifest)


def test_load_class_raises_for_a_missing_class_attribute(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _write_module(tmp_path, monkeypatch, "sample_missing_class", _VALID_PLUGIN_SOURCE)
    loader = PluginLoader()
    manifest = _manifest(entry_point="sample_missing_class:DoesNotExist")

    with pytest.raises(PluginLoadError):
        loader.load_class(manifest)


def test_load_class_raises_when_not_a_plugin_subclass(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _write_module(tmp_path, monkeypatch, "sample_not_a_plugin", _NOT_A_PLUGIN_SOURCE)
    loader = PluginLoader()
    manifest = _manifest(entry_point="sample_not_a_plugin:NotAPlugin")

    with pytest.raises(PluginLoadError):
        loader.load_class(manifest)


def test_load_instantiates_the_plugin(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _write_module(tmp_path, monkeypatch, "sample_load_ok", _VALID_PLUGIN_SOURCE)
    loader = PluginLoader()
    manifest = _manifest(entry_point="sample_load_ok:SamplePlugin")

    instance = loader.load(manifest)

    assert isinstance(instance, Plugin)
    assert instance.started is False  # type: ignore[attr-defined]


def test_load_raises_when_the_class_cannot_be_instantiated(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _write_module(tmp_path, monkeypatch, "sample_abstract", _ABSTRACT_PLUGIN_SOURCE)
    loader = PluginLoader()
    manifest = _manifest(entry_point="sample_abstract:IncompletePlugin")

    with pytest.raises(PluginLoadError):
        loader.load(manifest)


def test_reload_reimports_and_reinstantiates(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _write_module(tmp_path, monkeypatch, "sample_reload", _VALID_PLUGIN_SOURCE)
    loader = PluginLoader()
    manifest = _manifest(entry_point="sample_reload:SamplePlugin")
    loader.load(manifest)

    instance = loader.reload(manifest)

    assert isinstance(instance, Plugin)


def test_forget_stops_tracking_a_loaded_module(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _write_module(tmp_path, monkeypatch, "sample_forget", _VALID_PLUGIN_SOURCE)
    loader = PluginLoader()
    manifest = _manifest(entry_point="sample_forget:SamplePlugin")
    loader.load_class(manifest)

    loader.forget("sample")

    assert loader.is_loaded("sample") is False


# --- unloader.py ---


def test_unloader_drops_the_module_and_loader_reference(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _write_module(tmp_path, monkeypatch, "sample_unload", _VALID_PLUGIN_SOURCE)
    loader = PluginLoader()
    manifest = _manifest(entry_point="sample_unload:SamplePlugin")
    loader.load_class(manifest)
    unloader = PluginUnloader(loader)

    unloader.unload(manifest)

    assert loader.is_loaded("sample") is False
    assert "sample_unload" not in sys.modules


# --- installer.py ---


def test_installer_install_registers_validates_and_grants_permissions() -> None:
    registry = PluginRegistry()
    permissions = PermissionRegistry()
    installer = PluginInstaller(registry, permissions)
    manifest = _manifest(permissions=frozenset({PluginPermission.NETWORK}))

    record = installer.install(manifest)

    assert record.lifecycle.state == PluginState.INSTALLED
    assert permissions.has_permission("sample", PluginPermission.NETWORK) is True


def test_installer_install_can_grant_fewer_permissions_than_requested() -> None:
    registry = PluginRegistry()
    permissions = PermissionRegistry()
    installer = PluginInstaller(registry, permissions)
    manifest = _manifest(
        permissions=frozenset({PluginPermission.NETWORK, PluginPermission.DATABASE})
    )

    installer.install(manifest, granted_permissions=frozenset({PluginPermission.NETWORK}))

    assert permissions.has_permission("sample", PluginPermission.NETWORK) is True
    assert permissions.has_permission("sample", PluginPermission.DATABASE) is False


def test_installer_install_raises_when_already_installed() -> None:
    registry = PluginRegistry()
    installer = PluginInstaller(registry, PermissionRegistry())
    installer.install(_manifest())

    with pytest.raises(PluginAlreadyInstalledError):
        installer.install(_manifest())


def test_installer_install_propagates_validation_failures() -> None:
    installer = PluginInstaller(PluginRegistry(), PermissionRegistry())
    incompatible = PluginManifest(
        metadata=PluginMetadata(
            plugin_id="sample", name="Sample", version="1.0.0", category=PluginType.AUTOMATION
        ),
        entry_point="sample_valid_plugin:SamplePlugin",
        compatibility=">=99.0.0",
    )

    with pytest.raises(VersionIncompatibleError):
        installer.install(incompatible)


# --- updater.py ---


async def test_updater_update_replaces_the_manifest_and_regrants_permissions() -> None:
    registry = PluginRegistry()
    permissions = PermissionRegistry()
    PluginInstaller(registry, permissions).install(_manifest(version="1.0.0"))
    updater = PluginUpdater(registry, permissions)
    new_manifest = _manifest(version="2.0.0", permissions=frozenset({PluginPermission.STORAGE}))

    record = await updater.update(new_manifest)

    assert record.manifest.metadata.version == "2.0.0"
    assert record.lifecycle.state == PluginState.INSTALLED
    assert permissions.has_permission("sample", PluginPermission.STORAGE) is True


async def test_updater_update_runs_the_registered_migration_hook() -> None:
    registry = PluginRegistry()
    permissions = PermissionRegistry()
    PluginInstaller(registry, permissions).install(_manifest(version="1.0.0"))
    migrations = MigrationRegistry()
    calls: list[tuple[str, str]] = []

    async def hook(from_version: str, to_version: str) -> None:
        calls.append((from_version, to_version))

    migrations.register("1.0.0", "2.0.0", hook)
    updater = PluginUpdater(registry, permissions, migrations)

    await updater.update(_manifest(version="2.0.0"))

    assert calls == [("1.0.0", "2.0.0")]


async def test_updater_update_raises_for_an_unregistered_plugin() -> None:
    updater = PluginUpdater(PluginRegistry(), PermissionRegistry())

    with pytest.raises(PluginNotFoundError):
        await updater.update(_manifest())


async def test_updater_update_raises_when_lifecycle_state_forbids_it() -> None:
    registry = PluginRegistry()
    permissions = PermissionRegistry()
    record = registry.register(_manifest(version="1.0.0"))
    # still DISCOVERED -- never installed, so UPDATING isn't a valid transition yet
    assert record.lifecycle.state == PluginState.DISCOVERED
    updater = PluginUpdater(registry, permissions)

    with pytest.raises(InvalidLifecycleTransitionError):
        await updater.update(_manifest(version="2.0.0"))
