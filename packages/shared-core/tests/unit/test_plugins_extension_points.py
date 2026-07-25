"""Tests for extensions.py, ui.py, backend.py, workflow.py, connector.py,
ai.py, hooks.py, and events.py.
"""

from __future__ import annotations

import pytest
from shared_core.events.base import EventType
from shared_core.plugins.ai import AiExtensions
from shared_core.plugins.backend import BackendExtensions
from shared_core.plugins.connector import ConnectorExtensions
from shared_core.plugins.events import (
    PluginEvent,
    PluginInstalledEvent,
    PluginUninstalledEvent,
    build_plugin_event,
)
from shared_core.plugins.exceptions import ExtensionPointNotFoundError, HookExecutionError
from shared_core.plugins.extensions import ExtensionRegistry
from shared_core.plugins.hooks import BEFORE_STARTUP, HookRegistry
from shared_core.plugins.ui import UiExtensions
from shared_core.plugins.workflow import WorkflowExtensions

# --- extensions.py ---


def test_extension_point_contribute_then_get_round_trips() -> None:
    registry = ExtensionRegistry()

    registry.point("demo").contribute("plugin-a", "widget-1", {"kind": "chart"})

    assert registry.point("demo").get("widget-1") == {"kind": "chart"}


def test_extension_point_get_raises_for_unregistered_name() -> None:
    registry = ExtensionRegistry()

    with pytest.raises(ExtensionPointNotFoundError):
        registry.point("demo").get("missing")


def test_extension_point_withdraw_removes_a_contribution() -> None:
    registry = ExtensionRegistry()
    registry.point("demo").contribute("plugin-a", "widget-1", "value")

    registry.point("demo").withdraw("widget-1")

    with pytest.raises(ExtensionPointNotFoundError):
        registry.point("demo").get("widget-1")


def test_extension_registry_withdraw_all_from_clears_every_point() -> None:
    registry = ExtensionRegistry()
    registry.point("a").contribute("plugin-a", "x", 1)
    registry.point("b").contribute("plugin-a", "y", 2)
    registry.point("b").contribute("plugin-b", "z", 3)

    registry.withdraw_all_from("plugin-a")

    assert registry.point("a").list_contributions() == []
    contributions_b = registry.point("b").list_contributions()
    assert [c.plugin_id for c in contributions_b] == ["plugin-b"]


def test_extension_registry_list_points() -> None:
    registry = ExtensionRegistry()
    registry.point("a")
    registry.point("b")

    assert set(registry.list_points()) == {"a", "b"}


# --- domain-specific extension wrappers ---


@pytest.mark.parametrize(
    ("extensions_cls", "namespace"),
    [
        (UiExtensions, "ui"),
        (BackendExtensions, "backend"),
        (WorkflowExtensions, "workflow"),
        (ConnectorExtensions, "connector"),
        (AiExtensions, "ai"),
    ],
)
def test_namespaced_extensions_scope_contributions_under_their_namespace(
    extensions_cls: type, namespace: str
) -> None:
    registry = ExtensionRegistry()
    extensions = extensions_cls(registry)

    extensions.register("category", "plugin-a", "thing", "value")

    assert extensions.get("category", "thing") == "value"
    assert registry.point(f"{namespace}.category").get("thing") == "value"


def test_namespaced_extensions_list_contributions() -> None:
    registry = ExtensionRegistry()
    extensions = UiExtensions(registry)
    extensions.register("menus", "plugin-a", "main-menu", {"label": "Home"})

    contributions = extensions.list_contributions("menus")

    assert len(contributions) == 1
    assert contributions[0].plugin_id == "plugin-a"


def test_namespaced_extensions_withdraw_all_from_only_touches_its_own_namespace() -> None:
    registry = ExtensionRegistry()
    ui = UiExtensions(registry)
    backend = BackendExtensions(registry)
    ui.register("menus", "plugin-a", "main-menu", "value")
    backend.register("services", "plugin-a", "svc", "value")

    ui.withdraw_all_from("plugin-a")

    assert ui.list_contributions("menus") == []
    assert len(backend.list_contributions("services")) == 1


# --- hooks.py ---


async def test_hook_registry_fires_callbacks_in_registration_order() -> None:
    registry = HookRegistry()
    calls: list[str] = []

    async def first(*args: object, **kwargs: object) -> None:
        calls.append("first")

    async def second(*args: object, **kwargs: object) -> None:
        calls.append("second")

    registry.register(BEFORE_STARTUP, "plugin-a", first)
    registry.register(BEFORE_STARTUP, "plugin-b", second)

    await registry.fire(BEFORE_STARTUP)

    assert calls == ["first", "second"]


async def test_hook_registry_fire_passes_through_args_and_kwargs() -> None:
    registry = HookRegistry()
    received: list[tuple[tuple[object, ...], dict[str, object]]] = []

    async def callback(*args: object, **kwargs: object) -> None:
        received.append((args, kwargs))

    registry.register("custom_hook", "plugin-a", callback)

    await registry.fire("custom_hook", "arg1", key="value")

    assert received == [(("arg1",), {"key": "value"})]


async def test_hook_registry_fire_collects_every_failure() -> None:
    registry = HookRegistry()

    async def failing_one(*args: object, **kwargs: object) -> None:
        raise RuntimeError("boom-1")

    async def failing_two(*args: object, **kwargs: object) -> None:
        raise RuntimeError("boom-2")

    registry.register(BEFORE_STARTUP, "plugin-a", failing_one)
    registry.register(BEFORE_STARTUP, "plugin-b", failing_two)

    with pytest.raises(HookExecutionError, match="boom-1"):
        await registry.fire(BEFORE_STARTUP)


async def test_hook_registry_fire_runs_every_callback_even_if_one_fails() -> None:
    registry = HookRegistry()
    calls: list[str] = []

    async def failing(*args: object, **kwargs: object) -> None:
        raise RuntimeError("boom")

    async def succeeding(*args: object, **kwargs: object) -> None:
        calls.append("ran")

    registry.register(BEFORE_STARTUP, "plugin-a", failing)
    registry.register(BEFORE_STARTUP, "plugin-b", succeeding)

    with pytest.raises(HookExecutionError):
        await registry.fire(BEFORE_STARTUP)

    assert calls == ["ran"]


def test_hook_registry_unregister_all_from_removes_only_that_plugin() -> None:
    registry = HookRegistry()

    async def callback(*args: object, **kwargs: object) -> None:
        return None

    registry.register(BEFORE_STARTUP, "plugin-a", callback)
    registry.register(BEFORE_STARTUP, "plugin-b", callback)

    registry.unregister_all_from("plugin-a")

    remaining = registry.registered_hooks(BEFORE_STARTUP)
    assert [r.plugin_id for r in remaining] == ["plugin-b"]


def test_hook_registry_registered_hooks_returns_empty_for_unused_hook() -> None:
    registry = HookRegistry()

    assert registry.registered_hooks("never_registered") == []


# --- events.py ---


def test_plugin_installed_event_has_the_expected_name_and_type() -> None:
    event = build_plugin_event(
        PluginInstalledEvent, source_service="plugin-svc", plugin_id="sample"
    )

    assert event.event_name == "plugin.installed"
    assert event.event_type == EventType.PLUGIN
    assert event.payload == {"plugin_id": "sample"}


def test_plugin_event_supports_extra_payload() -> None:
    event = build_plugin_event(
        PluginUninstalledEvent, source_service="plugin-svc", plugin_id="sample", reason="cleanup"
    )

    assert event.payload["reason"] == "cleanup"


def test_plugin_event_is_a_base_event_subclass() -> None:
    event = build_plugin_event(
        PluginInstalledEvent, source_service="plugin-svc", plugin_id="sample"
    )

    assert isinstance(event, PluginEvent)
