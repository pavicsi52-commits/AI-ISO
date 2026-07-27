"""Builds the ``WEBHOOK`` node handler -- a genuine outbound HTTP call,
never simulated. ``node.config`` names ``url`` (required), ``method``
(default ``"POST"``), and ``payload`` (merged with the run's own
current variables).
"""

from __future__ import annotations

from typing import Any

import httpx
from shared_core.workflow import (
    NodeDefinition,
    NodeHandler,
    NodeHandlerRegistry,
    NodeType,
    TaskExecutionError,
    WorkflowContext,
)


def build_webhook_handler(client: httpx.AsyncClient) -> NodeHandler:
    """Build the handler registered for ``WEBHOOK`` nodes."""

    async def handle_webhook_node(node: NodeDefinition, context: WorkflowContext) -> dict[str, Any]:
        url = node.config.get("url")
        if not url:
            raise TaskExecutionError(
                f"Webhook node {node.node_id!r} has no 'url' in its own config."
            )
        method = str(node.config.get("method", "POST")).upper()
        payload = dict(node.config.get("payload", {}))
        payload.update(context.variables.as_dict())
        try:
            response = await client.request(method, str(url), json=payload)
        except httpx.HTTPError as exc:
            raise TaskExecutionError(
                f"Webhook node {node.node_id!r} request failed: {exc}"
            ) from exc
        return {"status_code": response.status_code}

    return handle_webhook_node


def register_webhook_handler(registry: NodeHandlerRegistry, client: httpx.AsyncClient) -> None:
    """Register the ``WEBHOOK`` node handler."""
    registry.register(NodeType.WEBHOOK, build_webhook_handler(client))


__all__ = ["build_webhook_handler", "register_webhook_handler"]
