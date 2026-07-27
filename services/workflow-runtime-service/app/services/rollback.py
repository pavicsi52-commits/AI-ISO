"""Manual workflow rollback. Per docs/042 "ROLLBACK" "Support": Workflow
Rollback, Step Rollback, Automatic Rollback, Manual Rollback, Rollback
Validation, Rollback Reports.

"Automatic Rollback" already happens for free inside
:class:`~app.services.execution.WorkflowExecutionService` -- the engine
itself calls ``shared_core.workflow.rollback.rollback_workflow`` on any
run that fails, since it's constructed with a populated
``CompensationRegistry``. This service is "Manual Rollback": a caller
explicitly asking to roll back an instance (typically one that already
finished, successfully or not) via ``POST /workflows/{id}/rollback``.
Since ``shared_core.workflow.execution.WorkflowExecution`` is a purely
in-memory object never persisted anywhere, this service reconstructs
one from this service's own durable
:class:`~app.models.workflow_execution_step.WorkflowExecutionStep` rows
before handing it to the same SDK function the engine itself uses.
"""

from __future__ import annotations

from uuid import UUID

from shared_core.workflow import (
    NodeExecutionResult,
    WorkflowContext,
    WorkflowExecution,
    WorkflowState,
)
from shared_core.workflow.rollback import rollback_workflow

from app.models.enums import NodeExecutionStatus, RollbackStatus, RollbackType
from app.repositories.workflow_execution_step import WorkflowExecutionStepRepository
from app.repositories.workflow_instance import WorkflowInstanceRepository
from app.services.compensation import WorkflowCompensationService, build_compensation_registry
from app.services.definition import WorkflowDefinitionService
from app.services.version import WorkflowVersionService

_TO_SDK_NODE_STATUS: dict[NodeExecutionStatus, WorkflowState] = {
    NodeExecutionStatus.PENDING: WorkflowState.CREATED,
    NodeExecutionStatus.RUNNING: WorkflowState.RUNNING,
    NodeExecutionStatus.COMPLETED: WorkflowState.COMPLETED,
    NodeExecutionStatus.FAILED: WorkflowState.FAILED,
    NodeExecutionStatus.ROLLED_BACK: WorkflowState.ROLLED_BACK,
    NodeExecutionStatus.SKIPPED: WorkflowState.CANCELLED,
}


class WorkflowRollbackService:
    """Rolls back an already-executed workflow instance on demand."""

    def __init__(
        self,
        instances: WorkflowInstanceRepository,
        steps: WorkflowExecutionStepRepository,
        definitions: WorkflowDefinitionService,
        versions: WorkflowVersionService,
        compensations: WorkflowCompensationService,
    ) -> None:
        self._instances = instances
        self._steps = steps
        self._definitions = definitions
        self._versions = versions
        self._compensations = compensations

    async def rollback(
        self,
        instance_id: UUID,
        *,
        node_ids: list[str] | None,
        rollback_type: RollbackType,
    ) -> tuple[RollbackStatus, list[str]]:
        """Roll back *instance_id*'s own completed nodes ("Workflow
        Rollback"/"Step Rollback").

        Raises:
            NotFoundError: If *instance_id* does not exist.
        """
        instance = await self._instances.require_by_id(instance_id)
        definition = await self._definitions.get_by_id(instance.definition_id)
        version = await self._versions.get_by_id(instance.version_id)

        execution = WorkflowExecution(
            execution_id=str(instance.id),
            workflow_id=definition.workflow_key,
            workflow_version=version.version_number,
        )
        for step in await self._steps.list_for_instance(instance_id):
            execution.record_node_result(
                NodeExecutionResult(
                    node_id=step.node_id,
                    status=_TO_SDK_NODE_STATUS.get(step.status, WorkflowState.CREATED),
                    started_at=step.started_at or step.created_at,
                    finished_at=step.finished_at,
                    output=step.output,
                    error=step.error,
                    attempts=step.attempts,
                )
            )

        compensations = build_compensation_registry(instance, version, self._compensations)
        context = WorkflowContext(
            workflow_id=definition.workflow_key,
            execution_id=str(instance.id),
            organization_id=str(instance.organization_id),
        )
        compensated = await rollback_workflow(execution, compensations, context, node_ids=node_ids)
        status = RollbackStatus.COMPLETED if compensated else RollbackStatus.FAILED
        return status, compensated


__all__ = ["WorkflowRollbackService"]
