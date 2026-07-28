"""AI assistant domain events.

Per docs/046 "EVENTS": ConversationStarted, ConversationCompleted,
ToolCalled, RecommendationGenerated, ReportGenerated, ModelChanged,
FeedbackReceived. "Integrate with Prompt 020" -- each is a
:class:`shared_core.events.base.DomainEvent` registered with
:data:`shared_core.events.registry.default_registry` at import time,
the same idiom every prior AI-IOS service established.
"""

from __future__ import annotations

from typing import ClassVar

from shared_core.events import default_registry
from shared_core.events.base import DomainEvent


@default_registry.register
class ConversationStartedEvent(DomainEvent):
    """A new conversation was opened."""

    event_name: ClassVar[str] = "ConversationStarted"


@default_registry.register
class ConversationCompletedEvent(DomainEvent):
    """A conversation reached a terminal state."""

    event_name: ClassVar[str] = "ConversationCompleted"


@default_registry.register
class ToolCalledEvent(DomainEvent):
    """A tool was invoked on the assistant's behalf."""

    event_name: ClassVar[str] = "ToolCalled"


@default_registry.register
class RecommendationGeneratedEvent(DomainEvent):
    """A recommendation was generated."""

    event_name: ClassVar[str] = "RecommendationGenerated"


@default_registry.register
class ReportGeneratedEvent(DomainEvent):
    """An AI-written report was generated."""

    event_name: ClassVar[str] = "ReportGenerated"


@default_registry.register
class ModelChangedEvent(DomainEvent):
    """An organization's own default model selection changed."""

    event_name: ClassVar[str] = "ModelChanged"


@default_registry.register
class FeedbackReceivedEvent(DomainEvent):
    """A user rated an assistant turn."""

    event_name: ClassVar[str] = "FeedbackReceived"


__all__ = [
    "ConversationCompletedEvent",
    "ConversationStartedEvent",
    "FeedbackReceivedEvent",
    "ModelChangedEvent",
    "RecommendationGeneratedEvent",
    "ReportGeneratedEvent",
    "ToolCalledEvent",
]
