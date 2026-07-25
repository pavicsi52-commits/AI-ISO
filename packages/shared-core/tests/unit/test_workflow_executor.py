"""Tests for executor.py."""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta

import pytest
from shared_core.workflow.context import WorkflowContext
from shared_core.workflow.exceptions import (
    ExpressionEvaluationError,
    TaskExecutionError,
    WorkflowTimeoutError,
)
from shared_core.workflow.executor import NodeExecutor, NodeHandlerRegistry
from shared_core.workflow.nodes import NodeDefinition, NodeType
from shared_core.workflow.variables import VariableScope


def _context(**variables: object) -> WorkflowContext:
    context = WorkflowContext(workflow_id="wf-1")
    for name, value in variables.items():
        context.variables.set(name, value, scope=VariableScope.RUNTIME)
    return context


# --- NodeHandlerRegistry ---


def test_registry_get_returns_none_when_unregistered() -> None:
    registry = NodeHandlerRegistry()

    assert registry.get(NodeType.TASK) is None


async def test_registry_register_then_get_round_trips() -> None:
    registry = NodeHandlerRegistry()

    async def handler(_node: NodeDefinition, _context: WorkflowContext) -> str:
        return "ok"

    registry.register(NodeType.TASK, handler)

    assert registry.get(NodeType.TASK) is handler


# --- structural no-ops ---


@pytest.mark.parametrize(
    "node_type", [NodeType.START, NodeType.END, NodeType.PARALLEL, NodeType.MERGE]
)
async def test_structural_noop_types_return_none(node_type: NodeType) -> None:
    executor = NodeExecutor(NodeHandlerRegistry())
    node = NodeDefinition(node_id="n1", node_type=node_type, name="n1")

    result = await executor.execute(node, _context())

    assert result is None


# --- delay/timer ---


async def test_delay_sleeps_for_configured_seconds() -> None:
    executor = NodeExecutor(NodeHandlerRegistry())
    node = NodeDefinition(
        node_id="n1", node_type=NodeType.DELAY, name="n1", config={"seconds": 0.01}
    )

    start = asyncio.get_event_loop().time()
    await executor.execute(node, _context())
    elapsed = asyncio.get_event_loop().time() - start

    assert elapsed >= 0.01


async def test_delay_defaults_to_zero_seconds() -> None:
    executor = NodeExecutor(NodeHandlerRegistry())
    node = NodeDefinition(node_id="n1", node_type=NodeType.DELAY, name="n1")

    await executor.execute(node, _context())  # doesn't hang


async def test_timer_without_at_is_a_no_op() -> None:
    executor = NodeExecutor(NodeHandlerRegistry())
    node = NodeDefinition(node_id="n1", node_type=NodeType.TIMER, name="n1")

    await executor.execute(node, _context())


async def test_timer_sleeps_until_the_configured_time() -> None:
    executor = NodeExecutor(NodeHandlerRegistry())
    target = (datetime.now(UTC) + timedelta(seconds=0.01)).isoformat()
    node = NodeDefinition(node_id="n1", node_type=NodeType.TIMER, name="n1", config={"at": target})

    await executor.execute(node, _context())

    assert datetime.now(UTC) >= datetime.fromisoformat(target)


async def test_timer_with_a_past_time_does_not_block() -> None:
    executor = NodeExecutor(NodeHandlerRegistry())
    target = (datetime.now(UTC) - timedelta(seconds=10)).isoformat()
    node = NodeDefinition(node_id="n1", node_type=NodeType.TIMER, name="n1", config={"at": target})

    await executor.execute(node, _context())


# --- condition/switch/script ---


async def test_condition_evaluates_the_configured_expression() -> None:
    executor = NodeExecutor(NodeHandlerRegistry())
    node = NodeDefinition(
        node_id="n1", node_type=NodeType.CONDITION, name="n1", config={"expression": "x > 5"}
    )

    result = await executor.execute(node, _context(x=10))

    assert result is True


async def test_condition_defaults_to_true_with_no_expression() -> None:
    executor = NodeExecutor(NodeHandlerRegistry())
    node = NodeDefinition(node_id="n1", node_type=NodeType.CONDITION, name="n1")

    result = await executor.execute(node, _context())

    assert result is True


async def test_switch_returns_the_matching_case() -> None:
    executor = NodeExecutor(NodeHandlerRegistry())
    node = NodeDefinition(
        node_id="n1",
        node_type=NodeType.SWITCH,
        name="n1",
        config={"cases": {"low": "x < 10", "high": "x >= 10"}},
    )

    result = await executor.execute(node, _context(x=20))

    assert result == "high"


async def test_script_evaluates_the_configured_expression() -> None:
    executor = NodeExecutor(NodeHandlerRegistry())
    node = NodeDefinition(
        node_id="n1", node_type=NodeType.SCRIPT, name="n1", config={"script": "x * 2"}
    )

    result = await executor.execute(node, _context(x=21))

    assert result == 42


async def test_script_raises_on_a_sandbox_violation() -> None:
    executor = NodeExecutor(NodeHandlerRegistry())
    node = NodeDefinition(
        node_id="n1",
        node_type=NodeType.SCRIPT,
        name="n1",
        config={"script": "''.__class__.__mro__[1].__subclasses__()"},
    )

    with pytest.raises(ExpressionEvaluationError):
        await executor.execute(node, _context())


# --- delegated handlers ---


async def test_delegated_node_calls_its_registered_handler() -> None:
    registry = NodeHandlerRegistry()
    calls: list[str] = []

    async def handler(node: NodeDefinition, _context: WorkflowContext) -> str:
        calls.append(node.node_id)
        return "handled"

    registry.register(NodeType.TASK, handler)
    executor = NodeExecutor(registry)
    node = NodeDefinition(node_id="n1", node_type=NodeType.TASK, name="n1")

    result = await executor.execute(node, _context())

    assert result == "handled"
    assert calls == ["n1"]


async def test_delegated_node_with_no_handler_raises() -> None:
    executor = NodeExecutor(NodeHandlerRegistry())
    node = NodeDefinition(node_id="n1", node_type=NodeType.CONNECTOR, name="n1")

    with pytest.raises(TaskExecutionError, match="No handler registered"):
        await executor.execute(node, _context())


async def test_delegated_node_wraps_a_handler_failure() -> None:
    registry = NodeHandlerRegistry()

    async def handler(_node: NodeDefinition, _context: WorkflowContext) -> None:
        raise RuntimeError("boom")

    registry.register(NodeType.TASK, handler)
    executor = NodeExecutor(registry)
    node = NodeDefinition(node_id="n1", node_type=NodeType.TASK, name="n1")

    with pytest.raises(TaskExecutionError):
        await executor.execute(node, _context())


async def test_delegated_node_respects_its_timeout() -> None:
    registry = NodeHandlerRegistry()

    async def handler(_node: NodeDefinition, _context: WorkflowContext) -> None:
        await asyncio.sleep(10)

    registry.register(NodeType.TASK, handler)
    executor = NodeExecutor(registry)
    node = NodeDefinition(node_id="n1", node_type=NodeType.TASK, name="n1", timeout_seconds=0.01)

    with pytest.raises(WorkflowTimeoutError):
        await executor.execute(node, _context())
