"""Agent platform domain events (docs/060 "EVENTS").

``AgentRegistered``, ``AgentStarted``, ``AgentCompleted``,
``AgentFailed``, ``TaskCreated``, ``TaskCompleted``, ``ToolInvoked``,
``ApprovalRequested``, ``EvaluationCompleted``. Each is a
:class:`shared_core.events.base.DomainEvent` registered with
:data:`shared_core.events.registry.default_registry` at import time,
the same idiom every prior AI-IOS service established (e.g.
``ai-assistant-service``'s own ``app/events/ai_events.py``, Prompt 046).
"""

from __future__ import annotations

from typing import ClassVar

from shared_core.events import default_registry
from shared_core.events.base import DomainEvent


@default_registry.register
class AgentRegisteredEvent(DomainEvent):
    """A new agent was registered."""

    event_name: ClassVar[str] = "AgentRegistered"


@default_registry.register
class AgentStartedEvent(DomainEvent):
    """An agent execution began."""

    event_name: ClassVar[str] = "AgentStarted"


@default_registry.register
class AgentCompletedEvent(DomainEvent):
    """An agent execution finished successfully."""

    event_name: ClassVar[str] = "AgentCompleted"


@default_registry.register
class AgentFailedEvent(DomainEvent):
    """An agent execution ended in failure."""

    event_name: ClassVar[str] = "AgentFailed"


@default_registry.register
class TaskCreatedEvent(DomainEvent):
    """A new agent task was created."""

    event_name: ClassVar[str] = "TaskCreated"


@default_registry.register
class TaskCompletedEvent(DomainEvent):
    """An agent task reached a terminal state."""

    event_name: ClassVar[str] = "TaskCompleted"


@default_registry.register
class ToolInvokedEvent(DomainEvent):
    """A tool was invoked (or denied) on an agent's behalf."""

    event_name: ClassVar[str] = "ToolInvoked"


@default_registry.register
class ApprovalRequestedEvent(DomainEvent):
    """An agent workflow paused for human approval."""

    event_name: ClassVar[str] = "ApprovalRequested"


@default_registry.register
class EvaluationCompletedEvent(DomainEvent):
    """An agent evaluation run finished."""

    event_name: ClassVar[str] = "EvaluationCompleted"


__all__ = [
    "AgentCompletedEvent",
    "AgentFailedEvent",
    "AgentRegisteredEvent",
    "AgentStartedEvent",
    "ApprovalRequestedEvent",
    "EvaluationCompletedEvent",
    "TaskCompletedEvent",
    "TaskCreatedEvent",
    "ToolInvokedEvent",
]
