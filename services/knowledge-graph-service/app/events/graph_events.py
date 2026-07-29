"""Knowledge graph domain events.

Per docs/049 "EVENTS": GraphNodeCreated, GraphNodeUpdated,
GraphRelationshipCreated, GraphRelationshipRemoved, GraphSynchronized,
GraphVersionCreated, ImpactAnalysisCompleted, BlastRadiusCalculated.
"Integrate with Prompt 020" -- each is a
:class:`shared_core.events.base.DomainEvent` registered with
:data:`shared_core.events.registry.default_registry` at import time.

Every one is genuinely published by the flow that owns its state
change; see ``app/services/``. Declaring events without emitting them
would make the integration decorative, a mistake this platform has
already made once and corrected.

**Node and relationship events carry keys, not payloads.** A subscriber
learning that ``inventory:host-42`` changed can read it back through the
API under its own credentials; broadcasting the node's properties would
push graph contents to every queue consumer regardless of what they may
see.
"""

from __future__ import annotations

from typing import ClassVar

from shared_core.events import default_registry
from shared_core.events.base import DomainEvent

SOURCE_SERVICE = "knowledge-graph-service"
"""Stamped on every event this service publishes."""


@default_registry.register
class GraphNodeCreatedEvent(DomainEvent):
    """A node was added to the graph."""

    event_name: ClassVar[str] = "GraphNodeCreated"


@default_registry.register
class GraphNodeUpdatedEvent(DomainEvent):
    """A node's properties changed."""

    event_name: ClassVar[str] = "GraphNodeUpdated"


@default_registry.register
class GraphRelationshipCreatedEvent(DomainEvent):
    """A relationship was created."""

    event_name: ClassVar[str] = "GraphRelationshipCreated"


@default_registry.register
class GraphRelationshipRemovedEvent(DomainEvent):
    """A relationship was removed."""

    event_name: ClassVar[str] = "GraphRelationshipRemoved"


@default_registry.register
class GraphSynchronizedEvent(DomainEvent):
    """A source finished synchronizing."""

    event_name: ClassVar[str] = "GraphSynchronized"


@default_registry.register
class GraphVersionCreatedEvent(DomainEvent):
    """A graph version was recorded."""

    event_name: ClassVar[str] = "GraphVersionCreated"


@default_registry.register
class ImpactAnalysisCompletedEvent(DomainEvent):
    """An impact analysis finished."""

    event_name: ClassVar[str] = "ImpactAnalysisCompleted"


@default_registry.register
class BlastRadiusCalculatedEvent(DomainEvent):
    """A blast-radius analysis finished."""

    event_name: ClassVar[str] = "BlastRadiusCalculated"


__all__ = [
    "SOURCE_SERVICE",
    "BlastRadiusCalculatedEvent",
    "GraphNodeCreatedEvent",
    "GraphNodeUpdatedEvent",
    "GraphRelationshipCreatedEvent",
    "GraphRelationshipRemovedEvent",
    "GraphSynchronizedEvent",
    "GraphVersionCreatedEvent",
    "ImpactAnalysisCompletedEvent",
]
