"""Tests for registry.py, manager.py, factory.py, and helpers.py."""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime

import pytest
import shared_core.workflow as workflow_package
from shared_core.workflow.context import WorkflowContext
from shared_core.workflow.definition import WorkflowDefinition
from shared_core.workflow.edges import EdgeDefinition
from shared_core.workflow.engine import WorkflowEngine
from shared_core.workflow.exceptions import (
    InvalidWorkflowDefinitionError,
    WorkflowNotFoundError,
)
from shared_core.workflow.execution import NodeExecutionResult, WorkflowExecution
from shared_core.workflow.executor import NodeExecutor, NodeHandlerRegistry
from shared_core.workflow.factory import create_workflow_framework
from shared_core.workflow.helpers import (
    execution_summary,
    format_duration,
    node_result_summary,
    workflow_summary,
)
from shared_core.workflow.manager import WorkflowManager
from shared_core.workflow.nodes import NodeDefinition, NodeType
from shared_core.workflow.parser import WorkflowBuilder
from shared_core.workflow.registry import WorkflowRegistry
from shared_core.workflow.state_machine import WorkflowState

# --- shared helpers ---


def _definition(version: str = "1.0.0") -> WorkflowDefinition:
    return (
        WorkflowBuilder("wf-1", "Sample", version=version)
        .node(NodeDefinition(node_id="start", node_type=NodeType.START, name="start"))
        .node(NodeDefinition(node_id="task", node_type=NodeType.TASK, name="task"))
        .node(NodeDefinition(node_id="end", node_type=NodeType.END, name="end"))
        .edge(EdgeDefinition(from_node_id="start", to_node_id="task"))
        .edge(EdgeDefinition(from_node_id="task", to_node_id="end"))
        .tag("sample")
        .owner("team-a")
        .build()
    )


def _invalid_definition() -> WorkflowDefinition:
    return (
        WorkflowBuilder("wf-bad", "Bad")
        .node(NodeDefinition(node_id="start", node_type=NodeType.START, name="start"))
        .build()
    )  # no END node


# --- registry.py ---


def test_registry_register_then_get_round_trips() -> None:
    registry = WorkflowRegistry()
    definition = _definition()

    registry.register(definition)

    assert registry.get("wf-1") == definition


def test_registry_get_defaults_to_latest_registered_version() -> None:
    registry = WorkflowRegistry()
    registry.register(_definition(version="1.0.0"))
    registry.register(_definition(version="2.0.0"))

    latest = registry.get("wf-1")

    assert latest.version == "2.0.0"


def test_registry_get_a_specific_version() -> None:
    registry = WorkflowRegistry()
    registry.register(_definition(version="1.0.0"))
    registry.register(_definition(version="2.0.0"))

    assert registry.get("wf-1", version="1.0.0").version == "1.0.0"


def test_registry_get_raises_for_unregistered_workflow() -> None:
    registry = WorkflowRegistry()

    with pytest.raises(WorkflowNotFoundError):
        registry.get("missing")


def test_registry_get_raises_for_unregistered_version() -> None:
    registry = WorkflowRegistry()
    registry.register(_definition(version="1.0.0"))

    with pytest.raises(WorkflowNotFoundError):
        registry.get("wf-1", version="9.9.9")


def test_registry_has_reports_registration_state() -> None:
    registry = WorkflowRegistry()

    assert registry.has("wf-1") is False

    registry.register(_definition())

    assert registry.has("wf-1") is True
    assert registry.has("wf-1", version="1.0.0") is True
    assert registry.has("wf-1", version="9.9.9") is False


def test_registry_unregister_a_single_version_keeps_others() -> None:
    registry = WorkflowRegistry()
    registry.register(_definition(version="1.0.0"))
    registry.register(_definition(version="2.0.0"))

    registry.unregister("wf-1", version="1.0.0")

    assert registry.list_versions("wf-1") == ["2.0.0"]


def test_registry_unregister_the_latest_version_promotes_the_remaining_one() -> None:
    registry = WorkflowRegistry()
    registry.register(_definition(version="1.0.0"))
    registry.register(_definition(version="2.0.0"))

    registry.unregister("wf-1", version="2.0.0")

    assert registry.get("wf-1").version == "1.0.0"


def test_registry_unregister_the_only_version_removes_the_workflow_entirely() -> None:
    registry = WorkflowRegistry()
    registry.register(_definition())

    registry.unregister("wf-1", version="1.0.0")

    assert registry.has("wf-1") is False


def test_registry_unregister_with_no_version_removes_everything() -> None:
    registry = WorkflowRegistry()
    registry.register(_definition(version="1.0.0"))
    registry.register(_definition(version="2.0.0"))

    registry.unregister("wf-1")

    assert registry.list_workflow_ids() == []


def test_registry_unregister_is_a_no_op_for_unregistered_workflow() -> None:
    registry = WorkflowRegistry()

    registry.unregister("missing")  # doesn't raise


def test_registry_list_workflow_ids_and_versions() -> None:
    registry = WorkflowRegistry()
    registry.register(_definition(version="1.0.0"))
    registry.register(_definition(version="2.0.0"))

    assert registry.list_workflow_ids() == ["wf-1"]
    assert registry.list_versions("wf-1") == ["1.0.0", "2.0.0"]


# --- manager.py ---


def _manager() -> WorkflowManager:
    executor = NodeExecutor(NodeHandlerRegistry())
    engine = WorkflowEngine(executor)
    return WorkflowManager(engine)


def test_manager_register_workflow_compiles_and_caches() -> None:
    manager = _manager()

    compiled = manager.register_workflow(_definition())

    assert compiled.definition.workflow_id == "wf-1"
    assert manager.compiled_workflow("wf-1") is compiled


def test_manager_register_workflow_twice_audits_an_update_not_a_create() -> None:
    manager = _manager()
    manager.register_workflow(_definition())

    manager.register_workflow(_definition())  # same (workflow_id, version) -> "update"

    assert manager.registry.list_versions("wf-1") == ["1.0.0"]


def test_manager_compiled_workflow_compiles_on_cache_miss() -> None:
    manager = _manager()
    manager.registry.register(_definition())  # bypasses register_workflow's own caching

    compiled = manager.compiled_workflow("wf-1")

    assert compiled.definition.workflow_id == "wf-1"


def test_manager_register_workflow_rejects_an_invalid_definition() -> None:
    manager = _manager()

    with pytest.raises(InvalidWorkflowDefinitionError):
        manager.register_workflow(_invalid_definition())


def test_manager_compiled_workflow_raises_for_unregistered_workflow() -> None:
    manager = _manager()

    with pytest.raises(WorkflowNotFoundError):
        manager.compiled_workflow("missing")


def test_manager_delete_workflow_removes_it_and_its_cache() -> None:
    manager = _manager()
    manager.register_workflow(_definition())

    manager.delete_workflow("wf-1")

    assert manager.registry.has("wf-1") is False
    with pytest.raises(WorkflowNotFoundError):
        manager.compiled_workflow("wf-1")


async def test_manager_start_and_wait_execution_runs_to_completion() -> None:
    handlers = NodeHandlerRegistry()

    async def task_handler(_node: NodeDefinition, _context: WorkflowContext) -> str:
        return "done"

    handlers.register(NodeType.TASK, task_handler)
    executor = NodeExecutor(handlers)
    engine = WorkflowEngine(executor)
    manager = WorkflowManager(engine)
    manager.register_workflow(_definition())
    context = WorkflowContext(workflow_id="wf-1")

    execution_id = await manager.start_execution("wf-1", context)

    assert execution_id == context.execution_id
    assert manager.is_execution_running(execution_id) is True
    execution = await manager.wait_execution(execution_id)

    assert execution.status == WorkflowState.COMPLETED
    assert execution_id in manager.list_execution_ids()
    assert manager.is_execution_running(execution_id) is False


async def test_manager_start_execution_raises_for_unregistered_workflow() -> None:
    manager = _manager()
    context = WorkflowContext(workflow_id="missing")

    with pytest.raises(WorkflowNotFoundError):
        await manager.start_execution("missing", context)


async def test_manager_cancel_execution_delegates_to_the_runtime() -> None:
    handlers = NodeHandlerRegistry()

    async def slow_handler(_node: NodeDefinition, _context: WorkflowContext) -> None:
        await asyncio.sleep(10)

    handlers.register(NodeType.TASK, slow_handler)
    executor = NodeExecutor(handlers)
    engine = WorkflowEngine(executor)
    manager = WorkflowManager(engine)
    manager.register_workflow(_definition())
    context = WorkflowContext(workflow_id="wf-1")

    execution_id = await manager.start_execution("wf-1", context)
    manager.cancel_execution(execution_id)

    with pytest.raises(asyncio.CancelledError):
        await manager.wait_execution(execution_id)


# --- factory.py ---


async def test_create_workflow_framework_wires_a_working_manager() -> None:
    handlers = NodeHandlerRegistry()

    async def task_handler(_node: NodeDefinition, _context: WorkflowContext) -> str:
        return "done"

    handlers.register(NodeType.TASK, task_handler)
    manager = create_workflow_framework(handlers)
    manager.register_workflow(_definition())
    context = WorkflowContext(workflow_id="wf-1")

    execution_id = await manager.start_execution("wf-1", context)
    execution = await manager.wait_execution(execution_id)

    assert execution.status == WorkflowState.COMPLETED


# --- helpers.py ---


@pytest.mark.parametrize(
    ("seconds", "expected"),
    [
        (5, "5s"),
        (90, "1m 30s"),
        (120, "2m"),
        (3661, "1h 1m"),
        (7200, "2h"),
    ],
)
def test_format_duration(seconds: float, expected: str) -> None:
    assert format_duration(seconds) == expected


def test_node_result_summary_is_json_serializable() -> None:

    result = NodeExecutionResult(
        node_id="task",
        status=WorkflowState.COMPLETED,
        started_at=datetime.now(UTC),
        finished_at=datetime.now(UTC),
        attempts=1,
    )

    summary = node_result_summary(result)

    assert summary["node_id"] == "task"
    assert summary["status"] == "completed"
    assert summary["duration_seconds"] is not None


def test_execution_summary_reports_completed_and_failed_nodes() -> None:
    execution = WorkflowExecution(execution_id="e1", workflow_id="wf-1", workflow_version="1.0.0")
    execution.record_node_result(
        NodeExecutionResult(
            node_id="a", status=WorkflowState.COMPLETED, started_at=execution.started_at
        )
    )
    execution.record_node_result(
        NodeExecutionResult(
            node_id="b", status=WorkflowState.FAILED, started_at=execution.started_at
        )
    )

    summary = execution_summary(execution)

    assert summary["completed_node_ids"] == ["a"]
    assert summary["failed_node_ids"] == ["b"]
    assert summary["duration_seconds"] is None


def test_workflow_summary_reports_counts_and_metadata() -> None:
    summary = workflow_summary(_definition())

    assert summary["workflow_id"] == "wf-1"
    assert summary["node_count"] == 3
    assert summary["edge_count"] == 2
    assert summary["tags"] == ["sample"]
    assert summary["owner"] == "team-a"


# --- __init__.py ---


def test_package_exports_are_all_importable() -> None:
    for name in workflow_package.__all__:
        assert hasattr(workflow_package, name)
