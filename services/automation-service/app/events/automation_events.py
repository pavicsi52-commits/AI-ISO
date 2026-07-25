"""Automation service domain events.

Per docs/040 "EVENTS": AutomationCreated, AutomationStarted,
AutomationCompleted, AutomationFailed, AutomationCancelled,
AutomationPaused, AutomationResumed, ApprovalRequested,
ApprovalGranted, RollbackStarted, RollbackCompleted,
ExecutionTimedOut. "Integrate with Prompt 020" -- each is a
:class:`shared_core.events.base.DomainEvent`, published via
:class:`shared_core.events.manager.EventManager`. Registered with
:data:`shared_core.events.registry.default_registry` at import time,
the same "@decorator, imported once at startup" idiom every prior
AI-IOS service established.
"""

from __future__ import annotations

from typing import ClassVar

from shared_core.events import default_registry
from shared_core.events.base import DomainEvent


@default_registry.register
class AutomationCreatedEvent(DomainEvent):
    """A new automation job was created."""

    event_name: ClassVar[str] = "AutomationCreated"


@default_registry.register
class AutomationStartedEvent(DomainEvent):
    """An automation execution started running."""

    event_name: ClassVar[str] = "AutomationStarted"


@default_registry.register
class AutomationCompletedEvent(DomainEvent):
    """An automation execution completed successfully."""

    event_name: ClassVar[str] = "AutomationCompleted"


@default_registry.register
class AutomationFailedEvent(DomainEvent):
    """An automation execution failed."""

    event_name: ClassVar[str] = "AutomationFailed"


@default_registry.register
class AutomationCancelledEvent(DomainEvent):
    """An automation execution was cancelled."""

    event_name: ClassVar[str] = "AutomationCancelled"


@default_registry.register
class AutomationPausedEvent(DomainEvent):
    """An automation execution was paused."""

    event_name: ClassVar[str] = "AutomationPaused"


@default_registry.register
class AutomationResumedEvent(DomainEvent):
    """An automation execution was resumed."""

    event_name: ClassVar[str] = "AutomationResumed"


@default_registry.register
class ApprovalRequestedEvent(DomainEvent):
    """An approval was requested for a pending automation execution."""

    event_name: ClassVar[str] = "ApprovalRequested"


@default_registry.register
class ApprovalGrantedEvent(DomainEvent):
    """An approval was granted for a pending automation execution."""

    event_name: ClassVar[str] = "ApprovalGranted"


@default_registry.register
class RollbackStartedEvent(DomainEvent):
    """A rollback operation began."""

    event_name: ClassVar[str] = "RollbackStarted"


@default_registry.register
class RollbackCompletedEvent(DomainEvent):
    """A rollback operation finished."""

    event_name: ClassVar[str] = "RollbackCompleted"


@default_registry.register
class ExecutionTimedOutEvent(DomainEvent):
    """An automation execution exceeded its own timeout."""

    event_name: ClassVar[str] = "ExecutionTimedOut"


__all__ = [
    "ApprovalGrantedEvent",
    "ApprovalRequestedEvent",
    "AutomationCancelledEvent",
    "AutomationCompletedEvent",
    "AutomationCreatedEvent",
    "AutomationFailedEvent",
    "AutomationPausedEvent",
    "AutomationResumedEvent",
    "AutomationStartedEvent",
    "ExecutionTimedOutEvent",
    "RollbackCompletedEvent",
    "RollbackStartedEvent",
]
