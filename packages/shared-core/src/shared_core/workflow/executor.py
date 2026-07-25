"""Node executor.

Per docs/028_Enterprise_Workflow_SDK.md.txt "NODE TYPES": executes a
single node according to its type. Structural types this SDK's own
logic fully defines (``START``, ``END``, ``PARALLEL``, ``MERGE``,
``DELAY``, ``TIMER``, ``CONDITION``, ``SWITCH``, ``SCRIPT``) are
executed directly -- ``PARALLEL``/``MERGE`` are pure fan-out/fan-in
markers with no behavior of their own, since
:func:`shared_core.workflow.dag.execution_plan`'s level grouping
already runs independent nodes concurrently regardless of their type;
``SCRIPT`` evaluates a sandboxed expression
(:mod:`shared_core.workflow.expressions`), never arbitrary code, for
the same injection-risk reason condition expressions are sandboxed.
Every other type (``TASK``, ``CONNECTOR``, ``PLUGIN``, ``AI``,
``WEBHOOK``, ``QUEUE``, ``EVENT``, ``HUMAN_TASK``, ``APPROVAL``,
``LOOP``, ``SUB_WORKFLOW``) delegates to a caller-registered async
handler via :class:`NodeHandlerRegistry` -- this framework provides the
dispatch mechanism, never business-specific implementations, per
docs/028 "DO NOT IMPLEMENT".
"""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime
from typing import Any

from shared_core.workflow.conditions import evaluate_if_else, evaluate_switch
from shared_core.workflow.context import WorkflowContext
from shared_core.workflow.exceptions import TaskExecutionError
from shared_core.workflow.expressions import evaluate_expression
from shared_core.workflow.nodes import NodeDefinition, NodeType
from shared_core.workflow.timeout import with_timeout

NodeHandler = Callable[[NodeDefinition, WorkflowContext], Awaitable[Any]]


class NodeHandlerRegistry:
    """Maps ``NodeType`` -> the async handler that executes it.

    Only business-delegated types need a registered handler; structural
    types (``START``/``END``/``PARALLEL``/``MERGE``/``DELAY``/``TIMER``/
    ``CONDITION``/``SWITCH``/``SCRIPT``) are executed by
    :class:`NodeExecutor` itself and never consult this registry.
    """

    def __init__(self) -> None:
        self._handlers: dict[NodeType, NodeHandler] = {}

    def register(self, node_type: NodeType, handler: NodeHandler) -> None:
        """Register *handler* for *node_type*."""
        self._handlers[node_type] = handler

    def get(self, node_type: NodeType) -> NodeHandler | None:
        """Return the registered handler for *node_type*, or ``None`` if unregistered."""
        return self._handlers.get(node_type)


class NodeExecutor:
    """Executes one node, dispatching structural types directly and delegating the rest."""

    def __init__(self, handlers: NodeHandlerRegistry) -> None:
        self._handlers = handlers
        self._structural_handlers: dict[NodeType, NodeHandler] = {
            NodeType.START: self._noop,
            NodeType.END: self._noop,
            NodeType.PARALLEL: self._noop,
            NodeType.MERGE: self._noop,
            NodeType.DELAY: self._delay,
            NodeType.TIMER: self._timer,
            NodeType.CONDITION: self._condition,
            NodeType.SWITCH: self._switch,
            NodeType.SCRIPT: self._script,
        }

    async def execute(self, node: NodeDefinition, context: WorkflowContext) -> Any:
        """Execute *node* and return its output.

        Raises:
            TaskExecutionError: If *node*'s type needs a registered
                handler and none is registered, or the handler itself raises.
            WorkflowTimeoutError: If a delegated node exceeds ``node.timeout_seconds``.
            ExpressionEvaluationError: If a ``CONDITION``/``SWITCH``/
                ``SCRIPT`` node's expression fails to evaluate.
        """
        handler = self._structural_handlers.get(node.node_type)
        if handler is not None:
            return await handler(node, context)
        return await with_timeout(
            self._execute_delegated(node, context),
            timeout_seconds=node.timeout_seconds,
            operation=f"Node {node.node_id!r}",
        )

    async def _noop(self, _node: NodeDefinition, _context: WorkflowContext) -> None:
        return None

    async def _delay(self, node: NodeDefinition, _context: WorkflowContext) -> None:
        seconds = float(node.config.get("seconds", 0))
        await asyncio.sleep(seconds)

    async def _timer(self, node: NodeDefinition, _context: WorkflowContext) -> None:
        target_iso = node.config.get("at")
        if target_iso is None:
            return
        target = datetime.fromisoformat(target_iso)
        remaining = (target - datetime.now(UTC)).total_seconds()
        if remaining > 0:
            await asyncio.sleep(remaining)

    async def _condition(self, node: NodeDefinition, context: WorkflowContext) -> bool:
        expression = node.config.get("expression", "true")
        return evaluate_if_else(expression, context.variables.as_dict(include_secrets=True))

    async def _switch(self, node: NodeDefinition, context: WorkflowContext) -> str | None:
        cases = node.config.get("cases", {})
        default = node.config.get("default")
        return evaluate_switch(
            cases, context.variables.as_dict(include_secrets=True), default=default
        )

    async def _script(self, node: NodeDefinition, context: WorkflowContext) -> Any:
        script = node.config.get("script", "")
        return evaluate_expression(script, context.variables.as_dict(include_secrets=True))

    async def _execute_delegated(self, node: NodeDefinition, context: WorkflowContext) -> Any:
        handler = self._handlers.get(node.node_type)
        if handler is None:
            raise TaskExecutionError(
                f"No handler registered for node type {node.node_type.value!r} "
                f"(node {node.node_id!r})."
            )
        try:
            return await handler(node, context)
        except Exception as exc:
            raise TaskExecutionError(f"Node {node.node_id!r} failed: {exc}") from exc


__all__ = ["NodeExecutor", "NodeHandler", "NodeHandlerRegistry"]
