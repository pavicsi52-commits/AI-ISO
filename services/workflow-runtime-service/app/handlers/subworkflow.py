"""Builds the ``SUB_WORKFLOW`` and ``LOOP`` node handlers.

Both delegate to an injected ``trigger_sub_workflow`` callback rather
than importing :mod:`app.services.execution` directly -- that service
is what builds the ``NodeHandlerRegistry`` these handlers register
into *before* it can call ``engine.run()``, so a direct import here
would be circular. ``app/services/execution.py`` supplies its own
``run_instance``-bound closure at registry-build time instead.

``LOOP`` is scoped to "run one sub-workflow once per item, collect
every result" ("Loop Execution") -- bounded by ``max_iterations``, the
same real, bounded-iteration discipline
``shared_core.workflow.constants.DEFAULT_LOOP_MAX_ITERATIONS`` already
establishes for the SDK's own loop-shaped constructs.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any

from shared_core.workflow import (
    MaxIterationsExceededError,
    NodeDefinition,
    NodeHandler,
    NodeHandlerRegistry,
    NodeType,
    TaskExecutionError,
    WorkflowContext,
)

TriggerSubWorkflow = Callable[[str, str | None, dict[str, Any]], Awaitable[dict[str, Any]]]
"""Called with ``(workflow_key, version, variables)``, returns the
nested run's own summary dict.
"""


def build_subworkflow_handler(trigger: TriggerSubWorkflow) -> NodeHandler:
    """Build the handler registered for ``SUB_WORKFLOW`` nodes."""

    async def handle_subworkflow_node(
        node: NodeDefinition, context: WorkflowContext
    ) -> dict[str, Any]:
        workflow_key = node.config.get("workflow_key")
        if not workflow_key:
            raise TaskExecutionError(
                f"Sub-workflow node {node.node_id!r} has no 'workflow_key' in its own config."
            )
        variables = dict(node.config.get("variables", {}))
        variables.update(context.variables.as_dict(include_secrets=True))
        return await trigger(str(workflow_key), node.config.get("version"), variables)

    return handle_subworkflow_node


def build_loop_handler(trigger: TriggerSubWorkflow, *, max_iterations: int) -> NodeHandler:
    """Build the handler registered for ``LOOP`` nodes."""

    async def handle_loop_node(
        node: NodeDefinition, context: WorkflowContext
    ) -> list[dict[str, Any]]:
        workflow_key = node.config.get("workflow_key")
        if not workflow_key:
            raise TaskExecutionError(
                f"Loop node {node.node_id!r} has no 'workflow_key' in its own config."
            )
        items = list(node.config.get("items", []))
        if len(items) > max_iterations:
            raise MaxIterationsExceededError(
                f"Loop node {node.node_id!r} has {len(items)} items, exceeding the "
                f"{max_iterations} maximum."
            )
        item_variable = str(node.config.get("item_variable", "item"))
        results: list[dict[str, Any]] = []
        for item in items:
            variables = context.variables.as_dict(include_secrets=True)
            variables[item_variable] = item
            results.append(await trigger(str(workflow_key), node.config.get("version"), variables))
        return results

    return handle_loop_node


def register_subworkflow_and_loop_handlers(
    registry: NodeHandlerRegistry, trigger: TriggerSubWorkflow, *, max_iterations: int
) -> None:
    """Register the ``SUB_WORKFLOW`` and ``LOOP`` node handlers."""
    registry.register(NodeType.SUB_WORKFLOW, build_subworkflow_handler(trigger))
    registry.register(NodeType.LOOP, build_loop_handler(trigger, max_iterations=max_iterations))


__all__ = [
    "TriggerSubWorkflow",
    "build_loop_handler",
    "build_subworkflow_handler",
    "register_subworkflow_and_loop_handlers",
]
