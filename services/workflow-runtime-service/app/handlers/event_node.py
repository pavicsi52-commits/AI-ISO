"""Builds the ``EVENT`` node handler -- publishes a
:class:`shared_core.events.base.DomainEvent` onto the platform-wide
event bus ("Integrate with Prompt 020"), letting a workflow notify any
other AI-IOS service without that service needing to poll this one.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any

from shared_core.events.base import DomainEvent
from shared_core.workflow import (
    NodeDefinition,
    NodeHandler,
    NodeHandlerRegistry,
    NodeType,
    WorkflowContext,
)

from app.events.workflow_events import WorkflowCustomEvent

EventPublisher = Callable[[DomainEvent], Awaitable[None]]


def build_event_handler(publish_event: EventPublisher) -> NodeHandler:
    """Build the handler registered for ``EVENT`` nodes."""

    async def handle_event_node(node: NodeDefinition, context: WorkflowContext) -> dict[str, Any]:
        payload = dict(node.config.get("payload", {}))
        payload.update({"workflow_id": context.workflow_id, "node_id": node.node_id})
        await publish_event(
            WorkflowCustomEvent(source_service="workflow-runtime-service", payload=payload)
        )
        return {"published": True}

    return handle_event_node


def register_event_handler(registry: NodeHandlerRegistry, publish_event: EventPublisher) -> None:
    """Register the ``EVENT`` node handler."""
    registry.register(NodeType.EVENT, build_event_handler(publish_event))


__all__ = ["build_event_handler", "register_event_handler"]
