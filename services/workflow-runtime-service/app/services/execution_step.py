"""Per-node execution results for a workflow instance, backing
``GET /workflow-instances/{id}/steps`` -- a read surface for the same
:class:`~app.models.workflow_execution_step.WorkflowExecutionStep` rows
:class:`~app.services.execution.WorkflowExecutionService` already
persists after every run, added directly (docs/042's own REST list has
no dedicated steps endpoint) the same "required capability with no REST
list entry" precedent the approval-decision endpoints already
established -- without it, a node's own per-step status/output/error is
otherwise invisible to any caller.
"""

from __future__ import annotations

from uuid import UUID

from app.models.workflow_execution_step import WorkflowExecutionStep
from app.repositories.workflow_execution_step import WorkflowExecutionStepRepository


class WorkflowExecutionStepService:
    """Reads per-node execution results for a workflow instance."""

    def __init__(self, steps: WorkflowExecutionStepRepository) -> None:
        self._steps = steps

    async def list_for_instance(self, instance_id: UUID) -> list[WorkflowExecutionStep]:
        """Every node execution result recorded for *instance_id*."""
        return await self._steps.list_for_instance(instance_id)


__all__ = ["WorkflowExecutionStepService"]
