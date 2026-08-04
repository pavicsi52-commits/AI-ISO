"""Domain events this service publishes (docs/053 "EVENTS").

Integrates ``shared_core.events`` (Prompt 020). Every class is registered
with :data:`shared_core.events.registry.default_registry` at import time
-- the publisher refuses an unregistered event, so without that decorator
every change write raises and the caller gets a 400 for a request that
did nothing wrong.
"""

from __future__ import annotations

from typing import ClassVar

from shared_core.events import default_registry
from shared_core.events.base import DomainEvent

SOURCE_SERVICE = "change-management-service"


@default_registry.register
class ChangeCreatedEvent(DomainEvent):
    """A new change request was opened."""

    event_name: ClassVar[str] = "ChangeCreated"


@default_registry.register
class ChangeSubmittedEvent(DomainEvent):
    """A change was submitted for risk assessment and approval."""

    event_name: ClassVar[str] = "ChangeSubmitted"


@default_registry.register
class RiskAssessmentCompletedEvent(DomainEvent):
    """A risk assessment was recorded against a change."""

    event_name: ClassVar[str] = "RiskAssessmentCompleted"


@default_registry.register
class ChangeApprovedEvent(DomainEvent):
    """A change's approval chain resolved to approved."""

    event_name: ClassVar[str] = "ChangeApproved"


@default_registry.register
class CabApprovedEvent(DomainEvent):
    """A Change Advisory Board review resolved to approved."""

    event_name: ClassVar[str] = "CABApproved"


@default_registry.register
class ChangeScheduledEvent(DomainEvent):
    """A change was scheduled into a maintenance window."""

    event_name: ClassVar[str] = "ChangeScheduled"


@default_registry.register
class ImplementationStartedEvent(DomainEvent):
    """A change's implementation began."""

    event_name: ClassVar[str] = "ImplementationStarted"


@default_registry.register
class ImplementationCompletedEvent(DomainEvent):
    """A change's implementation finished."""

    event_name: ClassVar[str] = "ImplementationCompleted"


@default_registry.register
class RollbackStartedEvent(DomainEvent):
    """A rollback began."""

    event_name: ClassVar[str] = "RollbackStarted"


@default_registry.register
class RollbackCompletedEvent(DomainEvent):
    """A rollback finished."""

    event_name: ClassVar[str] = "RollbackCompleted"


@default_registry.register
class PirCompletedEvent(DomainEvent):
    """A post-implementation review was approved."""

    event_name: ClassVar[str] = "PIRCompleted"


__all__ = [
    "SOURCE_SERVICE",
    "CabApprovedEvent",
    "ChangeApprovedEvent",
    "ChangeCreatedEvent",
    "ChangeScheduledEvent",
    "ChangeSubmittedEvent",
    "ImplementationCompletedEvent",
    "ImplementationStartedEvent",
    "PirCompletedEvent",
    "RiskAssessmentCompletedEvent",
    "RollbackCompletedEvent",
    "RollbackStartedEvent",
]
