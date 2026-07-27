"""Workflow runtime service domain events.

Per docs/042 "EVENTS": WorkflowStarted, WorkflowPaused, WorkflowResumed,
WorkflowCheckpointed, WorkflowCompleted, WorkflowFailed,
WorkflowCancelled, WorkflowRolledBack, ApprovalRequested,
ApprovalCompleted, ReplayStarted, ReplayCompleted. "Integrate with
Prompt 020" -- each is a :class:`shared_core.events.base.DomainEvent`,
published via :class:`shared_core.events.manager.EventManager`.
Registered with :data:`shared_core.events.registry.default_registry` at
import time, the same "@decorator, imported once at startup" idiom
every prior AI-IOS service established.

Distinct from ``shared_core.workflow.events.WorkflowEvent`` and its own
subclasses (``WorkflowStartedEvent``, etc.) -- those are the SDK's own
purely in-process notification objects passed to
``WorkflowEngine``'s ``on_event`` callback, never published onto the
platform-wide RabbitMQ-backed event bus themselves. This module's own
events ARE what actually crosses that bus; ``app/services/execution.py``
translates one into the other inside its own ``on_event`` handler.
"""

from __future__ import annotations

from typing import ClassVar

from shared_core.events import default_registry
from shared_core.events.base import DomainEvent


@default_registry.register
class WorkflowStartedEvent(DomainEvent):
    """A workflow instance started running."""

    event_name: ClassVar[str] = "WorkflowStarted"


@default_registry.register
class WorkflowPausedEvent(DomainEvent):
    """A workflow instance was paused."""

    event_name: ClassVar[str] = "WorkflowPaused"


@default_registry.register
class WorkflowResumedEvent(DomainEvent):
    """A workflow instance was resumed."""

    event_name: ClassVar[str] = "WorkflowResumed"


@default_registry.register
class WorkflowCheckpointedEvent(DomainEvent):
    """A workflow instance's own progress was checkpointed."""

    event_name: ClassVar[str] = "WorkflowCheckpointed"


@default_registry.register
class WorkflowCompletedEvent(DomainEvent):
    """A workflow instance completed successfully."""

    event_name: ClassVar[str] = "WorkflowCompleted"


@default_registry.register
class WorkflowFailedEvent(DomainEvent):
    """A workflow instance failed."""

    event_name: ClassVar[str] = "WorkflowFailed"


@default_registry.register
class WorkflowCancelledEvent(DomainEvent):
    """A workflow instance was cancelled."""

    event_name: ClassVar[str] = "WorkflowCancelled"


@default_registry.register
class WorkflowRolledBackEvent(DomainEvent):
    """A workflow instance was rolled back."""

    event_name: ClassVar[str] = "WorkflowRolledBack"


@default_registry.register
class ApprovalRequestedEvent(DomainEvent):
    """A human-approval gate was requested."""

    event_name: ClassVar[str] = "ApprovalRequested"


@default_registry.register
class ApprovalCompletedEvent(DomainEvent):
    """A human-approval gate was decided."""

    event_name: ClassVar[str] = "ApprovalCompleted"


@default_registry.register
class ReplayStartedEvent(DomainEvent):
    """A workflow replay run started."""

    event_name: ClassVar[str] = "ReplayStarted"


@default_registry.register
class ReplayCompletedEvent(DomainEvent):
    """A workflow replay run completed."""

    event_name: ClassVar[str] = "ReplayCompleted"


@default_registry.register
class WorkflowCustomEvent(DomainEvent):
    """A caller-defined event a workflow's own ``EVENT`` node published."""

    event_name: ClassVar[str] = "WorkflowCustomEvent"


__all__ = [
    "ApprovalCompletedEvent",
    "ApprovalRequestedEvent",
    "ReplayCompletedEvent",
    "ReplayStartedEvent",
    "WorkflowCancelledEvent",
    "WorkflowCheckpointedEvent",
    "WorkflowCompletedEvent",
    "WorkflowCustomEvent",
    "WorkflowFailedEvent",
    "WorkflowPausedEvent",
    "WorkflowResumedEvent",
    "WorkflowRolledBackEvent",
    "WorkflowStartedEvent",
]
