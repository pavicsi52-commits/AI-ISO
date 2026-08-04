"""Domain events this service publishes (docs/052 "EVENTS").

Integrates ``shared_core.events`` (Prompt 020). Every class is registered
with :data:`shared_core.events.registry.default_registry` at import time
-- the publisher refuses an unregistered event, so without that decorator
every incident write raises and the caller gets a 400 for a request that
did nothing wrong.

**No event fires per timeline entry or per worklog note.** An active
incident can accumulate dozens of both, and an event each would be a
firehose nobody could subscribe to usefully. What subscribers actually
want is the lifecycle transitions and the exceptional cases -- creation,
assignment, escalation, resolution, closure, and major-incident
declaration -- which is exactly the set docs/052 names.
"""

from __future__ import annotations

from typing import ClassVar

from shared_core.events import default_registry
from shared_core.events.base import DomainEvent

SOURCE_SERVICE = "incident-management-service"


@default_registry.register
class IncidentCreatedEvent(DomainEvent):
    """A new incident was opened."""

    event_name: ClassVar[str] = "IncidentCreated"


@default_registry.register
class IncidentAssignedEvent(DomainEvent):
    """An incident was assigned or reassigned."""

    event_name: ClassVar[str] = "IncidentAssigned"


@default_registry.register
class IncidentAcknowledgedEvent(DomainEvent):
    """An incident was acknowledged, stopping its acknowledgement SLA."""

    event_name: ClassVar[str] = "IncidentAcknowledged"


@default_registry.register
class IncidentEscalatedEvent(DomainEvent):
    """An escalation fired."""

    event_name: ClassVar[str] = "IncidentEscalated"


@default_registry.register
class IncidentResolvedEvent(DomainEvent):
    """An incident was marked resolved."""

    event_name: ClassVar[str] = "IncidentResolved"


@default_registry.register
class IncidentClosedEvent(DomainEvent):
    """An incident was closed."""

    event_name: ClassVar[str] = "IncidentClosed"


@default_registry.register
class IncidentReopenedEvent(DomainEvent):
    """A resolved or closed incident moved back to active work.

    Kept distinct from ``IncidentCreated`` and the ordinary status-change
    machinery: a reopen is the specific, operationally significant claim
    that a fix did not hold, and a trend dashboard needs to be able to
    count it as such rather than as an unremarkable transition.
    """

    event_name: ClassVar[str] = "IncidentReopened"


@default_registry.register
class MajorIncidentDeclaredEvent(DomainEvent):
    """An incident was declared major."""

    event_name: ClassVar[str] = "MajorIncidentDeclared"


@default_registry.register
class PostmortemCompletedEvent(DomainEvent):
    """A postmortem was approved and published."""

    event_name: ClassVar[str] = "PostmortemCompleted"


@default_registry.register
class ProblemCreatedEvent(DomainEvent):
    """A recurring pattern was recorded as a problem."""

    event_name: ClassVar[str] = "ProblemCreated"


__all__ = [
    "SOURCE_SERVICE",
    "IncidentAcknowledgedEvent",
    "IncidentAssignedEvent",
    "IncidentClosedEvent",
    "IncidentCreatedEvent",
    "IncidentEscalatedEvent",
    "IncidentReopenedEvent",
    "IncidentResolvedEvent",
    "MajorIncidentDeclaredEvent",
    "PostmortemCompletedEvent",
    "ProblemCreatedEvent",
]
