"""Small, dependency-free utility functions shared across the SDK."""

from __future__ import annotations

from typing import Any

from shared_core.workflow.definition import WorkflowDefinition
from shared_core.workflow.execution import NodeExecutionResult, WorkflowExecution
from shared_core.workflow.state_machine import WorkflowState

_SECONDS_PER_MINUTE = 60
_MINUTES_PER_HOUR = 60


def format_duration(seconds: float) -> str:
    """Format a duration in seconds as a compact human-readable string (e.g. ``"2m 30s"``)."""
    total_seconds = round(seconds)
    if total_seconds < _SECONDS_PER_MINUTE:
        return f"{total_seconds}s"
    minutes, secs = divmod(total_seconds, _SECONDS_PER_MINUTE)
    if minutes < _MINUTES_PER_HOUR:
        return f"{minutes}m {secs}s" if secs else f"{minutes}m"
    hours, mins = divmod(minutes, _MINUTES_PER_HOUR)
    return f"{hours}h {mins}m" if mins else f"{hours}h"


def node_result_summary(result: NodeExecutionResult) -> dict[str, Any]:
    """A JSON-serializable summary of one node's outcome."""
    return {
        "node_id": result.node_id,
        "status": result.status.value,
        "started_at": result.started_at.isoformat(),
        "finished_at": result.finished_at.isoformat() if result.finished_at else None,
        "duration_seconds": result.duration_seconds,
        "attempts": result.attempts,
        "error": result.error,
    }


def execution_summary(execution: WorkflowExecution) -> dict[str, Any]:
    """A JSON-serializable summary of *execution*'s current state."""
    duration = None
    if execution.finished_at is not None:
        duration = (execution.finished_at - execution.started_at).total_seconds()
    failed = [
        node_id
        for node_id, result in execution.node_results.items()
        if result.status == WorkflowState.FAILED
    ]
    return {
        "execution_id": execution.execution_id,
        "workflow_id": execution.workflow_id,
        "workflow_version": execution.workflow_version,
        "status": execution.status.value,
        "started_at": execution.started_at.isoformat(),
        "finished_at": execution.finished_at.isoformat() if execution.finished_at else None,
        "duration_seconds": duration,
        "completed_node_ids": execution.completed_node_ids(),
        "failed_node_ids": failed,
    }


def workflow_summary(definition: WorkflowDefinition) -> dict[str, Any]:
    """A JSON-serializable summary of a workflow definition."""
    return {
        "workflow_id": definition.workflow_id,
        "name": definition.name,
        "version": definition.version,
        "node_count": len(definition.nodes),
        "edge_count": len(definition.edges),
        "tags": list(definition.tags),
        "owner": definition.owner,
        "created_at": definition.created_at.isoformat(),
    }


__all__ = [
    "execution_summary",
    "format_duration",
    "node_result_summary",
    "workflow_summary",
]
