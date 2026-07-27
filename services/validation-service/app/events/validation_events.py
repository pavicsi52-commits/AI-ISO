"""Validation service domain events.

Per docs/043 "EVENTS": ValidationStarted, ValidationCompleted,
ValidationFailed, ValidationPassed, ValidationCancelled,
ValidationProfileCreated, ValidationRuleUpdated,
ValidationRemediationGenerated, ValidationScoreChanged. "Integrate with
Prompt 020" -- each is a :class:`shared_core.events.base.DomainEvent`,
published via :class:`shared_core.events.manager.EventManager`,
registered with :data:`shared_core.events.registry.default_registry` at
import time, the same "@decorator, imported once at startup" idiom
every prior AI-IOS service established.
"""

from __future__ import annotations

from typing import ClassVar

from shared_core.events import default_registry
from shared_core.events.base import DomainEvent


@default_registry.register
class ValidationStartedEvent(DomainEvent):
    """A validation execution started running."""

    event_name: ClassVar[str] = "ValidationStarted"


@default_registry.register
class ValidationCompletedEvent(DomainEvent):
    """A validation execution reached a terminal status."""

    event_name: ClassVar[str] = "ValidationCompleted"


@default_registry.register
class ValidationFailedEvent(DomainEvent):
    """A validation execution's own aggregate outcome was a failure."""

    event_name: ClassVar[str] = "ValidationFailed"


@default_registry.register
class ValidationPassedEvent(DomainEvent):
    """A validation execution's own aggregate outcome was a pass."""

    event_name: ClassVar[str] = "ValidationPassed"


@default_registry.register
class ValidationCancelledEvent(DomainEvent):
    """A validation execution was cancelled."""

    event_name: ClassVar[str] = "ValidationCancelled"


@default_registry.register
class ValidationProfileCreatedEvent(DomainEvent):
    """A new validation profile was created."""

    event_name: ClassVar[str] = "ValidationProfileCreated"


@default_registry.register
class ValidationRuleUpdatedEvent(DomainEvent):
    """A validation rule was created or changed."""

    event_name: ClassVar[str] = "ValidationRuleUpdated"


@default_registry.register
class ValidationRemediationGeneratedEvent(DomainEvent):
    """A new remediation suggestion was generated for a failure."""

    event_name: ClassVar[str] = "ValidationRemediationGenerated"


@default_registry.register
class ValidationScoreChangedEvent(DomainEvent):
    """An execution's own weighted score was computed or changed."""

    event_name: ClassVar[str] = "ValidationScoreChanged"


__all__ = [
    "ValidationCancelledEvent",
    "ValidationCompletedEvent",
    "ValidationFailedEvent",
    "ValidationPassedEvent",
    "ValidationProfileCreatedEvent",
    "ValidationRemediationGeneratedEvent",
    "ValidationRuleUpdatedEvent",
    "ValidationScoreChangedEvent",
    "ValidationStartedEvent",
]
