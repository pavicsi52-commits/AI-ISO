"""The ``AI`` node handler -- the core "LangGraph node" for a multi-
agent graph: one node dispatches to one real agent via
:class:`~app.agents.orchestrator.AgentOrchestrator`.

Mirrors ``workflow-runtime-service``'s own ``app/handlers/webhook.py``
shape (a plain closure over whatever the handler needs, registered
into a fresh :class:`~shared_core.workflow.NodeHandlerRegistry` per
run). ``node.config`` names ``description`` (falls back to the node's
own ``name``) and ``agent_type`` (falls back to
:attr:`~app.models.enums.AgentType.EXECUTOR`).
"""

from __future__ import annotations

from typing import Any

from shared_core.workflow import (
    NodeDefinition,
    NodeHandler,
    NodeHandlerRegistry,
    NodeType,
    TaskExecutionError,
    VariableScope,
    WorkflowContext,
)

from app.agents.orchestrator import AgentOrchestrator, AgentTask, SharedMemory
from app.models.enums import AgentType


def build_ai_node_handler(orchestrator: AgentOrchestrator) -> NodeHandler:
    """Build the handler registered for ``AI`` nodes."""

    async def handle_ai_node(node: NodeDefinition, context: WorkflowContext) -> dict[str, Any]:
        description = str(node.config.get("description", node.name))
        raw_agent_type = node.config.get("agent_type", str(AgentType.EXECUTOR))
        try:
            agent_type = AgentType(raw_agent_type)
        except ValueError as exc:
            raise TaskExecutionError(
                f"AI node {node.node_id!r} names unknown agent_type {raw_agent_type!r}."
            ) from exc

        task = AgentTask(description=description, agent_type=agent_type)
        result = await orchestrator.run_one(task, SharedMemory())
        if not result.succeeded:
            raise TaskExecutionError(
                f"AI node {node.node_id!r} failed: {result.error or 'unknown error'}."
            )

        context.variables.set(
            f"{node.node_id}_result", result.content, scope=VariableScope.WORKFLOW
        )
        return {"content": result.content, "agent_name": result.agent_name}

    return handle_ai_node


def register_ai_node_handler(
    registry: NodeHandlerRegistry, orchestrator: AgentOrchestrator
) -> None:
    """Register the ``AI`` node handler."""
    registry.register(NodeType.AI, build_ai_node_handler(orchestrator))


__all__ = ["build_ai_node_handler", "register_ai_node_handler"]
