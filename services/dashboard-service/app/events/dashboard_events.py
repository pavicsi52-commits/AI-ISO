"""Dashboard domain events.

Per docs/048 "EVENTS": DashboardCreated, DashboardUpdated,
DashboardDeleted, WidgetAdded, WidgetRemoved, LayoutChanged,
DashboardShared. "Integrate with Prompt 020" -- each is a
:class:`shared_core.events.base.DomainEvent` registered with
:data:`shared_core.events.registry.default_registry` at import time.

Every one is genuinely published by the flow that owns its state
change; see ``app/services/``. Declaring events without emitting them
would make the integration decorative, a mistake this platform has
already made once and corrected.
"""

from __future__ import annotations

from typing import ClassVar

from shared_core.events import default_registry
from shared_core.events.base import DomainEvent

SOURCE_SERVICE = "dashboard-service"
"""Stamped on every event this service publishes."""


@default_registry.register
class DashboardCreatedEvent(DomainEvent):
    """A dashboard was created."""

    event_name: ClassVar[str] = "DashboardCreated"


@default_registry.register
class DashboardUpdatedEvent(DomainEvent):
    """A dashboard's own settings changed."""

    event_name: ClassVar[str] = "DashboardUpdated"


@default_registry.register
class DashboardDeletedEvent(DomainEvent):
    """A dashboard was deleted."""

    event_name: ClassVar[str] = "DashboardDeleted"


@default_registry.register
class WidgetAddedEvent(DomainEvent):
    """A widget was added to a dashboard."""

    event_name: ClassVar[str] = "WidgetAdded"


@default_registry.register
class WidgetRemovedEvent(DomainEvent):
    """A widget was removed from a dashboard."""

    event_name: ClassVar[str] = "WidgetRemoved"


@default_registry.register
class LayoutChangedEvent(DomainEvent):
    """A dashboard layout was saved or restored."""

    event_name: ClassVar[str] = "LayoutChanged"


@default_registry.register
class DashboardSharedEvent(DomainEvent):
    """A dashboard was shared."""

    event_name: ClassVar[str] = "DashboardShared"


__all__ = [
    "SOURCE_SERVICE",
    "DashboardCreatedEvent",
    "DashboardDeletedEvent",
    "DashboardSharedEvent",
    "DashboardUpdatedEvent",
    "LayoutChangedEvent",
    "WidgetAddedEvent",
    "WidgetRemovedEvent",
]
