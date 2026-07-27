"""Builds the ``QUEUE`` node handler using
``shared_core.workflow.queue.WorkflowTaskQueue`` directly -- the SDK's
own real, ready-made envelope/producer for "publish and don't wait"
work, scoped exactly to this one node type per its own docstring.
"""

from __future__ import annotations

from typing import Any

from shared_core.workflow import (
    NodeDefinition,
    NodeHandler,
    NodeHandlerRegistry,
    NodeType,
    WorkflowContext,
    WorkflowTaskQueue,
)


def build_queue_handler(task_queue: WorkflowTaskQueue) -> NodeHandler:
    """Build the handler registered for ``QUEUE`` nodes."""

    async def handle_queue_node(node: NodeDefinition, context: WorkflowContext) -> dict[str, Any]:
        payload = dict(node.config.get("payload", {}))
        await task_queue.enqueue(context.execution_id, node.node_id, payload)
        return {"enqueued": True}

    return handle_queue_node


def register_queue_handler(registry: NodeHandlerRegistry, task_queue: WorkflowTaskQueue) -> None:
    """Register the ``QUEUE`` node handler."""
    registry.register(NodeType.QUEUE, build_queue_handler(task_queue))


__all__ = ["build_queue_handler", "register_queue_handler"]
