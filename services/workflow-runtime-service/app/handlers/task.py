"""Builds the ``TASK``/``CONNECTOR`` node handler.

Mirrors the exact shape ``services/automation-service``'s own
``app/workflow/handlers.py::build_automation_task_handler`` already
established for this purpose (built in Prompt 040 but never wired into
a live engine there, since that service owns no ``WorkflowEngine`` of
its own) -- reimplemented here rather than imported, since AI-IOS
services never share code across service boundaries, only through
``packages/shared-core``; ``shared_core.workflow`` itself defines no
such function (confirmed at runtime: it is automation-service's own
module-level helper, not part of the SDK). See
``app/clients/automation_client.py``'s own docstring for why
``CONNECTOR`` nodes are dispatched identically to ``TASK`` nodes rather
than this service reimplementing SSH/WinRM/etc. itself.
"""

from __future__ import annotations

from typing import Any
from uuid import UUID

from shared_core.workflow import (
    NodeDefinition,
    NodeHandler,
    NodeHandlerRegistry,
    NodeType,
    TaskExecutionError,
    WorkflowContext,
)

from app.clients.automation_client import AutomationClient


def build_task_and_connector_handler(client: AutomationClient) -> NodeHandler:
    """Build the one handler registered for both ``TASK`` and ``CONNECTOR`` nodes."""

    async def handle_task_node(node: NodeDefinition, context: WorkflowContext) -> dict[str, Any]:
        job_id_raw = node.config.get("job_id")
        if job_id_raw is None:
            raise TaskExecutionError(
                f"Workflow node {node.node_id!r} has no 'job_id' in its own config."
            )
        target_ids_raw = node.config.get("target_ids", [])
        variables: dict[str, Any] = dict(node.config.get("variables", {}))
        variables.update(context.variables.as_dict(include_secrets=True))
        return await client.execute_and_wait(
            UUID(str(job_id_raw)),
            variables=variables,
            target_ids=[UUID(str(target_id)) for target_id in target_ids_raw],
        )

    return handle_task_node


def register_task_and_connector_handlers(
    registry: NodeHandlerRegistry, client: AutomationClient
) -> None:
    """Register the same handler for both ``TASK`` and ``CONNECTOR`` node types."""
    handler = build_task_and_connector_handler(client)
    registry.register(NodeType.TASK, handler)
    registry.register(NodeType.CONNECTOR, handler)


__all__ = ["build_task_and_connector_handler", "register_task_and_connector_handlers"]
