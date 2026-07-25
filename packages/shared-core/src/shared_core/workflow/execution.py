"""Workflow execution state.

Per docs/028_Enterprise_Workflow_SDK.md.txt "WORKFLOW PRINCIPLES":
"Every execution is persistent", "Every step is traceable." The
runtime record of one workflow run -- distinct from the static
:class:`~shared_core.workflow.definition.WorkflowDefinition` -- tracks
each node's outcome and the run's overall state machine.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from shared_core.workflow.state_machine import StateMachine, WorkflowState


@dataclass(slots=True)
class NodeExecutionResult:
    """One node's outcome within a workflow execution ("Every step is traceable")."""

    node_id: str
    status: WorkflowState
    started_at: datetime
    finished_at: datetime | None = None
    output: Any = None
    error: str | None = None
    attempts: int = 1

    @property
    def duration_seconds(self) -> float | None:
        """Wall-clock time this node took, or ``None`` if still running."""
        if self.finished_at is None:
            return None
        return (self.finished_at - self.started_at).total_seconds()


@dataclass(slots=True)
class WorkflowExecution:
    """One run of a workflow definition ("Every execution is persistent")."""

    execution_id: str
    workflow_id: str
    workflow_version: str
    state_machine: StateMachine = field(default_factory=StateMachine)
    node_results: dict[str, NodeExecutionResult] = field(default_factory=dict)
    started_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    finished_at: datetime | None = None

    @property
    def status(self) -> WorkflowState:
        """This execution's current overall state."""
        return self.state_machine.state

    def record_node_result(self, result: NodeExecutionResult) -> None:
        """Record (or overwrite, on retry) one node's outcome."""
        self.node_results[result.node_id] = result

    def completed_node_ids(self) -> list[str]:
        """Every node id that finished ``COMPLETED``, for resume/checkpoint purposes."""
        return [
            node_id
            for node_id, result in self.node_results.items()
            if result.status == WorkflowState.COMPLETED
        ]


__all__ = ["NodeExecutionResult", "WorkflowExecution"]
