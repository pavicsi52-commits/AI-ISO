"""``/workflows`` and its ``execute``/``pause``/``resume``/``cancel``/
``rollback``/``replay`` actions. Per docs/042 REST list.

``pause``/``resume``/``cancel``/``rollback``/``replay`` all act on
*workflow_id*'s own most recent, still-active instance -- see
``app/services/instance.py``'s own module docstring for why, and for
the honest cooperative-only limitation of pause/resume/cancel.
"""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter
from shared_core.exceptions.not_found import NotFoundError
from shared_core.logging.context import get_log_context

from app.api.deps import (
    CurrentUserId,
    CurrentUserToken,
    DefinitionSvc,
    InstanceSvc,
    QueueProducerDep,
    ReplaySvc,
    RollbackSvc,
    VersionSvc,
)
from app.models.enums import WorkflowTriggerType
from app.models.workflow_definition import WorkflowDefinition
from app.models.workflow_instance import WorkflowInstance
from app.schemas.instance import WorkflowInstanceResponse
from app.schemas.replay import WorkflowReplayRequest, WorkflowReplayResponse
from app.schemas.response import ResponseMeta, SuccessResponse
from app.schemas.rollback import WorkflowRollbackRequest, WorkflowRollbackResponse
from app.schemas.workflow import (
    WorkflowCreateRequest,
    WorkflowExecuteRequest,
    WorkflowResponse,
    WorkflowUpdateRequest,
)
from app.workers.execution_worker import EXECUTION_QUEUE_NAME

router = APIRouter(prefix="/workflows", tags=["Workflows"])


def _meta() -> ResponseMeta:
    return ResponseMeta(request_id=get_log_context().request_id or "unknown")


def workflow_to_response(definition: WorkflowDefinition) -> WorkflowResponse:
    return WorkflowResponse(
        id=definition.id,
        organization_id=definition.organization_id,
        project_id=definition.project_id,
        workflow_key=definition.workflow_key,
        name=definition.name,
        description=definition.description,
        owner=definition.owner,
        tags=definition.tags,
        default_variables=definition.default_variables,
        current_version_number=definition.current_version_number,
    )


def instance_to_response(instance: WorkflowInstance) -> WorkflowInstanceResponse:
    return WorkflowInstanceResponse(
        id=instance.id,
        organization_id=instance.organization_id,
        project_id=instance.project_id,
        definition_id=instance.definition_id,
        version_id=instance.version_id,
        parent_instance_id=instance.parent_instance_id,
        sdk_execution_id=instance.sdk_execution_id,
        status=instance.status,
        trigger_type=instance.trigger_type,
        triggered_by=instance.triggered_by,
        started_at=instance.started_at,
        finished_at=instance.finished_at,
        error_message=instance.error_message,
    )


@router.get("", response_model=SuccessResponse[list[WorkflowResponse]])
async def list_workflows(
    organization_id: UUID, definitions: DefinitionSvc, _caller: CurrentUserId
) -> SuccessResponse[list[WorkflowResponse]]:
    """List every workflow definition in *organization_id*."""
    records = await definitions.list_for_org(organization_id)
    data = [workflow_to_response(record) for record in records]
    return SuccessResponse(message="Workflows retrieved.", data=data, meta=_meta())


@router.get("/{workflow_id}", response_model=SuccessResponse[WorkflowResponse])
async def get_workflow(
    workflow_id: UUID, definitions: DefinitionSvc, _caller: CurrentUserId
) -> SuccessResponse[WorkflowResponse]:
    """Return one workflow definition.

    Raises:
        NotFoundError: If no such workflow exists.
    """
    definition = await definitions.get_by_id(workflow_id)
    return SuccessResponse(
        message="Workflow retrieved.", data=workflow_to_response(definition), meta=_meta()
    )


@router.post("", response_model=SuccessResponse[WorkflowResponse], status_code=201)
async def create_workflow(
    body: WorkflowCreateRequest, definitions: DefinitionSvc, _caller: CurrentUserId
) -> SuccessResponse[WorkflowResponse]:
    """Define a new workflow and its own first DAG version ("Create").

    Raises:
        ConflictError: If ``workflow_key`` is already used in this organization.
        InvalidWorkflowDefinitionError: If the given DAG is structurally invalid.
        CycleDetectedError: If the given DAG contains a cycle ("Cycle Detection").
    """
    definition = await definitions.create(
        organization_id=body.organization_id,
        project_id=body.project_id,
        workflow_key=body.workflow_key,
        name=body.name,
        description=body.description,
        owner=body.owner,
        tags=body.tags,
        default_variables=body.default_variables,
        nodes=[node.model_dump(mode="json") for node in body.nodes],
        edges=[edge.model_dump(mode="json") for edge in body.edges],
    )
    return SuccessResponse(
        message="Workflow created.", data=workflow_to_response(definition), meta=_meta()
    )


@router.put("/{workflow_id}", response_model=SuccessResponse[WorkflowResponse])
async def update_workflow(
    workflow_id: UUID,
    body: WorkflowUpdateRequest,
    definitions: DefinitionSvc,
    _caller: CurrentUserId,
) -> SuccessResponse[WorkflowResponse]:
    """Replace a workflow's own metadata and record a new DAG version ("Update").

    Raises:
        NotFoundError: If no such workflow exists.
        InvalidWorkflowDefinitionError: If the given DAG is structurally invalid.
        CycleDetectedError: If the given DAG contains a cycle.
    """
    definition = await definitions.update(
        workflow_id,
        name=body.name,
        description=body.description,
        owner=body.owner,
        tags=body.tags,
        default_variables=body.default_variables,
        nodes=[node.model_dump(mode="json") for node in body.nodes],
        edges=[edge.model_dump(mode="json") for edge in body.edges],
    )
    return SuccessResponse(
        message="Workflow updated.", data=workflow_to_response(definition), meta=_meta()
    )


@router.delete("/{workflow_id}", response_model=SuccessResponse[dict[str, bool]])
async def delete_workflow(
    workflow_id: UUID, definitions: DefinitionSvc, _caller: CurrentUserId
) -> SuccessResponse[dict[str, bool]]:
    """Soft-delete a workflow definition ("Delete")."""
    await definitions.delete(workflow_id)
    return SuccessResponse(message="Workflow deleted.", data={"success": True}, meta=_meta())


@router.post(
    "/{workflow_id}/execute",
    response_model=SuccessResponse[WorkflowInstanceResponse],
    status_code=201,
)
async def execute_workflow(
    workflow_id: UUID,
    body: WorkflowExecuteRequest,
    definitions: DefinitionSvc,
    versions: VersionSvc,
    instances: InstanceSvc,
    caller: CurrentUserId,
    caller_token: CurrentUserToken,
    queue_producer: QueueProducerDep,
) -> SuccessResponse[WorkflowInstanceResponse]:
    """Create a new instance of a workflow and enqueue it for dispatch
    ("Execute"/"Async Execution") -- the actual run happens in
    :mod:`app.workers.execution_worker`, not on this request.

    Raises:
        NotFoundError: If no such workflow exists, or it has no version yet.
    """
    definition = await definitions.get_by_id(workflow_id)
    version = await versions.get_latest_for_definition(workflow_id)
    if version is None:
        raise NotFoundError(f"Workflow {workflow_id!r} has no version yet.")
    instance = await instances.create(
        organization_id=definition.organization_id,
        project_id=definition.project_id,
        definition_id=workflow_id,
        version_id=version.id,
        trigger_type=WorkflowTriggerType.MANUAL,
        triggered_by=caller,
    )
    await queue_producer.publish(
        EXECUTION_QUEUE_NAME,
        {
            "instance_id": str(instance.id),
            "caller_token": caller_token,
            "variables": body.variables,
        },
    )
    return SuccessResponse(
        message="Workflow execution enqueued.", data=instance_to_response(instance), meta=_meta()
    )


@router.post("/{workflow_id}/pause", response_model=SuccessResponse[WorkflowInstanceResponse])
async def pause_workflow(
    workflow_id: UUID, instances: InstanceSvc, _caller: CurrentUserId
) -> SuccessResponse[WorkflowInstanceResponse]:
    """Record caller intent to pause *workflow_id*'s own active instance ("Pause")."""
    active = await instances.get_active_for_definition(workflow_id)
    paused = await instances.pause(active.id)
    return SuccessResponse(
        message="Workflow instance paused.", data=instance_to_response(paused), meta=_meta()
    )


@router.post("/{workflow_id}/resume", response_model=SuccessResponse[WorkflowInstanceResponse])
async def resume_workflow(
    workflow_id: UUID, instances: InstanceSvc, _caller: CurrentUserId
) -> SuccessResponse[WorkflowInstanceResponse]:
    """Mark *workflow_id*'s own active instance as runnable again ("Resume")."""
    active = await instances.get_active_for_definition(workflow_id)
    resumed = await instances.resume(active.id)
    return SuccessResponse(
        message="Workflow instance resumed.", data=instance_to_response(resumed), meta=_meta()
    )


@router.post("/{workflow_id}/cancel", response_model=SuccessResponse[WorkflowInstanceResponse])
async def cancel_workflow(
    workflow_id: UUID, instances: InstanceSvc, _caller: CurrentUserId
) -> SuccessResponse[WorkflowInstanceResponse]:
    """Record caller intent to cancel *workflow_id*'s own active instance ("Cancel")."""
    active = await instances.get_active_for_definition(workflow_id)
    cancelled = await instances.cancel(active.id)
    return SuccessResponse(
        message="Workflow instance cancelled.", data=instance_to_response(cancelled), meta=_meta()
    )


@router.post("/{workflow_id}/rollback", response_model=SuccessResponse[WorkflowRollbackResponse])
async def rollback_workflow_route(
    workflow_id: UUID,
    body: WorkflowRollbackRequest,
    instances: InstanceSvc,
    rollback: RollbackSvc,
    _caller: CurrentUserId,
) -> SuccessResponse[WorkflowRollbackResponse]:
    """Roll back *workflow_id*'s own active instance ("Workflow Rollback"/"Step Rollback")."""
    active = await instances.get_active_for_definition(workflow_id)
    status, compensated = await rollback.rollback(
        active.id, node_ids=body.node_ids, rollback_type=body.rollback_type
    )
    data = WorkflowRollbackResponse(
        instance_id=active.id,
        rollback_type=body.rollback_type,
        status=status,
        compensated_node_ids=compensated,
    )
    return SuccessResponse(message="Workflow rollback completed.", data=data, meta=_meta())


@router.post("/{workflow_id}/replay", response_model=SuccessResponse[WorkflowReplayResponse])
async def replay_workflow(
    workflow_id: UUID,
    body: WorkflowReplayRequest,
    instances: InstanceSvc,
    replay: ReplaySvc,
    caller: CurrentUserId,
    caller_token: CurrentUserToken,
) -> SuccessResponse[WorkflowReplayResponse]:
    """Replay *workflow_id*'s own active instance as a new run ("Replay Workflow"/
    "Replay Failed Steps"/"Replay From Checkpoint").
    """
    active = await instances.get_active_for_definition(workflow_id)
    record = await replay.replay(
        active.id,
        replay_type=body.replay_type,
        checkpoint_id=body.checkpoint_id,
        requested_by=caller,
        caller_token=caller_token,
    )
    data = WorkflowReplayResponse(
        id=record.id,
        instance_id=record.instance_id,
        new_instance_id=record.new_instance_id,
        replay_type=record.replay_type,
        source_checkpoint_id=record.source_checkpoint_id,
        requested_by=record.requested_by,
        requested_at=record.requested_at,
        comparison=record.comparison,
    )
    return SuccessResponse(message="Workflow replay completed.", data=data, meta=_meta())


__all__ = ["instance_to_response", "router", "workflow_to_response"]
