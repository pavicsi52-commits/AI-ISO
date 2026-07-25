"""Plugin domain events.

Per docs/029_Enterprise_Plugin_Framework.md.txt "AUDIT"-adjacent
lifecycle moments (Install, Enable, Disable, Update, Uninstall,
Failures), formalized as :class:`~shared_core.events.base.BaseEvent`
subclasses (Prompt 020) the same way
:mod:`shared_core.workflow.events` does for workflow lifecycle --
``EventType.PLUGIN`` was added to the shared ``EventType`` enum for
this prompt (unlike ``EventType.WORKFLOW``, no plugin category
pre-existed).
"""

from __future__ import annotations

from typing import ClassVar

from shared_core.events.base import BaseEvent, EventType


class PluginEvent(BaseEvent):
    """Base class every plugin lifecycle event inherits."""

    event_type: ClassVar[EventType] = EventType.PLUGIN


class PluginInstalledEvent(PluginEvent):
    """A plugin was installed ("Install")."""

    event_name: ClassVar[str] = "plugin.installed"


class PluginEnabledEvent(PluginEvent):
    """A plugin was enabled ("Enable")."""

    event_name: ClassVar[str] = "plugin.enabled"


class PluginDisabledEvent(PluginEvent):
    """A plugin was disabled ("Disable")."""

    event_name: ClassVar[str] = "plugin.disabled"


class PluginStartedEvent(PluginEvent):
    """A plugin was started ("Start")."""

    event_name: ClassVar[str] = "plugin.started"


class PluginStoppedEvent(PluginEvent):
    """A plugin was stopped ("Stop")."""

    event_name: ClassVar[str] = "plugin.stopped"


class PluginUpdatedEvent(PluginEvent):
    """A plugin was updated to a new version ("Update")."""

    event_name: ClassVar[str] = "plugin.updated"


class PluginUninstalledEvent(PluginEvent):
    """A plugin was uninstalled ("Uninstall")."""

    event_name: ClassVar[str] = "plugin.uninstalled"


class PluginFailedEvent(PluginEvent):
    """A plugin operation failed ("Failures")."""

    event_name: ClassVar[str] = "plugin.failed"


def build_plugin_event(
    event_cls: type[PluginEvent], *, source_service: str, plugin_id: str, **extra_payload: object
) -> PluginEvent:
    """Build one of this module's event classes with a consistent payload shape."""
    payload: dict[str, object] = {"plugin_id": plugin_id}
    payload.update(extra_payload)
    return event_cls(source_service=source_service, payload=payload)


__all__ = [
    "PluginDisabledEvent",
    "PluginEnabledEvent",
    "PluginEvent",
    "PluginFailedEvent",
    "PluginInstalledEvent",
    "PluginStartedEvent",
    "PluginStoppedEvent",
    "PluginUninstalledEvent",
    "PluginUpdatedEvent",
    "build_plugin_event",
]
