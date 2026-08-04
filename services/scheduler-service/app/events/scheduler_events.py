"""Domain events this service publishes (docs/054 "EVENTS").

Integrates ``shared_core.events`` (Prompt 020). Every class is registered
with :data:`shared_core.events.registry.default_registry` at import time
-- the publisher refuses an unregistered event, so without that decorator
every job write raises and the caller gets a 400 for a request that did
nothing wrong.
"""

from __future__ import annotations

from typing import ClassVar

from shared_core.events import default_registry
from shared_core.events.base import DomainEvent

SOURCE_SERVICE = "scheduler-service"


@default_registry.register
class JobScheduledEvent(DomainEvent):
    """A job's next due time was (re)computed."""

    event_name: ClassVar[str] = "JobScheduled"


@default_registry.register
class JobStartedEvent(DomainEvent):
    """A job's execution was dispatched."""

    event_name: ClassVar[str] = "JobStarted"


@default_registry.register
class JobCompletedEvent(DomainEvent):
    """A job's execution finished successfully."""

    event_name: ClassVar[str] = "JobCompleted"


@default_registry.register
class JobFailedEvent(DomainEvent):
    """A job's execution failed."""

    event_name: ClassVar[str] = "JobFailed"


@default_registry.register
class JobRetriedEvent(DomainEvent):
    """A failed execution was scheduled for another attempt."""

    event_name: ClassVar[str] = "JobRetried"


@default_registry.register
class JobCancelledEvent(DomainEvent):
    """A job's execution, or the job itself, was cancelled."""

    event_name: ClassVar[str] = "JobCancelled"


@default_registry.register
class MaintenanceStartedEvent(DomainEvent):
    """A maintenance window became active."""

    event_name: ClassVar[str] = "MaintenanceStarted"


@default_registry.register
class MaintenanceEndedEvent(DomainEvent):
    """A maintenance window ended."""

    event_name: ClassVar[str] = "MaintenanceEnded"


@default_registry.register
class SchedulerRecoveredEvent(DomainEvent):
    """A terminal failure was manually recovered."""

    event_name: ClassVar[str] = "SchedulerRecovered"


__all__ = [
    "SOURCE_SERVICE",
    "JobCancelledEvent",
    "JobCompletedEvent",
    "JobFailedEvent",
    "JobRetriedEvent",
    "JobScheduledEvent",
    "JobStartedEvent",
    "MaintenanceEndedEvent",
    "MaintenanceStartedEvent",
    "SchedulerRecoveredEvent",
]
