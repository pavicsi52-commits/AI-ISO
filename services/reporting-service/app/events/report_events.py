"""Reporting domain events.

Per docs/047 "EVENTS": ReportCreated, ReportGenerated, ReportFailed,
ReportScheduled, ReportDelivered, ReportDownloaded, ReportArchived.
"Integrate with Prompt 020" -- each is a
:class:`shared_core.events.base.DomainEvent` registered with
:data:`shared_core.events.registry.default_registry` at import time.

Every one of these is genuinely published by the flow that owns its
state change; see ``app/services/`` for where. Declaring events without
emitting them would make the integration decorative, which is a mistake
this platform has already made once and corrected.
"""

from __future__ import annotations

from typing import ClassVar

from shared_core.events import default_registry
from shared_core.events.base import DomainEvent

SOURCE_SERVICE = "reporting-service"
"""Stamped on every event this service publishes."""


@default_registry.register
class ReportCreatedEvent(DomainEvent):
    """A saved report definition was created."""

    event_name: ClassVar[str] = "ReportCreated"


@default_registry.register
class ReportGeneratedEvent(DomainEvent):
    """A report execution completed successfully."""

    event_name: ClassVar[str] = "ReportGenerated"


@default_registry.register
class ReportFailedEvent(DomainEvent):
    """A report execution failed."""

    event_name: ClassVar[str] = "ReportFailed"


@default_registry.register
class ReportScheduledEvent(DomainEvent):
    """A report schedule was created or updated."""

    event_name: ClassVar[str] = "ReportScheduled"


@default_registry.register
class ReportDeliveredEvent(DomainEvent):
    """A rendered artifact was delivered over a channel."""

    event_name: ClassVar[str] = "ReportDelivered"


@default_registry.register
class ReportDownloadedEvent(DomainEvent):
    """A rendered artifact was downloaded."""

    event_name: ClassVar[str] = "ReportDownloaded"


@default_registry.register
class ReportArchivedEvent(DomainEvent):
    """A rendered artifact was archived."""

    event_name: ClassVar[str] = "ReportArchived"


__all__ = [
    "SOURCE_SERVICE",
    "ReportArchivedEvent",
    "ReportCreatedEvent",
    "ReportDeliveredEvent",
    "ReportDownloadedEvent",
    "ReportFailedEvent",
    "ReportGeneratedEvent",
    "ReportScheduledEvent",
]
