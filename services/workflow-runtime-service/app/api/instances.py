"""``/workflow-instances`` and its ``logs``/``checkpoints``/``approvals``
actions. Per docs/042 REST list, plus the approval-decision endpoints
added directly -- see ``app/schemas/approval.py``'s own docstring for
why.
"""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter
from shared_core.logging.context import get_log_context

from app.api.deps import (
    ApprovalSvc,
    CheckpointSvc,
    CurrentUserId,
    ExecutionStepSvc,
    InstanceSvc,
    LogSvc,
)
from app.api.workflows import instance_to_response
from app.models.enums import WorkflowInstanceStatus
from app.models.workflow_approval import WorkflowApproval
from app.models.workflow_checkpoint import WorkflowCheckpoint
from app.models.workflow_execution_step import WorkflowExecutionStep
from app.models.workflow_log import WorkflowLog
from app.schemas.approval import WorkflowApprovalDecisionRequest, WorkflowApprovalResponse
from app.schemas.checkpoint import WorkflowCheckpointResponse
from app.schemas.execution_step import WorkflowExecutionStepResponse
from app.schemas.instance import WorkflowInstanceResponse
from app.schemas.log import WorkflowLogResponse
from app.schemas.response import ResponseMeta, SuccessResponse

router = APIRouter(prefix="/workflow-instances", tags=["Workflow Instances"])


def _meta() -> ResponseMeta:
    return ResponseMeta(request_id=get_log_context().request_id or "unknown")


def checkpoint_to_response(checkpoint: WorkflowCheckpoint) -> WorkflowCheckpointResponse:
    return WorkflowCheckpointResponse(
        id=checkpoint.id,
        instance_id=checkpoint.instance_id,
        checkpoint_type=checkpoint.checkpoint_type,
        state=checkpoint.state,
        completed_node_ids=checkpoint.completed_node_ids,
        checkpointed_at=checkpoint.checkpointed_at,
    )


def log_to_response(log: WorkflowLog) -> WorkflowLogResponse:
    return WorkflowLogResponse(
        id=log.id,
        instance_id=log.instance_id,
        node_id=log.node_id,
        level=log.level,
        message=log.message,
        logged_at=log.logged_at,
    )


def execution_step_to_response(step: WorkflowExecutionStep) -> WorkflowExecutionStepResponse:
    return WorkflowExecutionStepResponse(
        id=step.id,
        instance_id=step.instance_id,
        node_id=step.node_id,
        node_type=step.node_type,
        status=step.status,
        started_at=step.started_at,
        finished_at=step.finished_at,
        output=step.output,
        error=step.error,
        attempts=step.attempts,
    )


def approval_to_response(approval: WorkflowApproval) -> WorkflowApprovalResponse:
    return WorkflowApprovalResponse(
        id=approval.id,
        instance_id=approval.instance_id,
        node_id=approval.node_id,
        node_type=approval.node_type,
        approvers=approval.approvers,
        required_approvals=approval.required_approvals,
        decision=approval.decision,
        decisions_by_approver=approval.decisions_by_approver,
        comments=approval.comments,
        escalated_to=approval.escalated_to,
        timeout_seconds=approval.timeout_seconds,
        decided_at=approval.decided_at,
    )


@router.get("", response_model=SuccessResponse[list[WorkflowInstanceResponse]])
async def list_instances(
    organization_id: UUID,
    instances: InstanceSvc,
    _caller: CurrentUserId,
    status: WorkflowInstanceStatus | None = None,
) -> SuccessResponse[list[WorkflowInstanceResponse]]:
    """List every workflow instance in *organization_id*."""
    records = await instances.list_for_org(organization_id, status=status)
    data = [instance_to_response(record) for record in records]
    return SuccessResponse(message="Workflow instances retrieved.", data=data, meta=_meta())


@router.get("/{instance_id}", response_model=SuccessResponse[WorkflowInstanceResponse])
async def get_instance(
    instance_id: UUID, instances: InstanceSvc, _caller: CurrentUserId
) -> SuccessResponse[WorkflowInstanceResponse]:
    """Return one workflow instance.

    Raises:
        NotFoundError: If no such instance exists.
    """
    instance = await instances.get_by_id(instance_id)
    return SuccessResponse(
        message="Workflow instance retrieved.", data=instance_to_response(instance), meta=_meta()
    )


@router.get("/{instance_id}/logs", response_model=SuccessResponse[list[WorkflowLogResponse]])
async def list_instance_logs(
    instance_id: UUID, logs: LogSvc, _caller: CurrentUserId
) -> SuccessResponse[list[WorkflowLogResponse]]:
    """List every log line recorded for a workflow instance."""
    records = await logs.list_for_instance(instance_id)
    data = [log_to_response(record) for record in records]
    return SuccessResponse(message="Workflow instance logs retrieved.", data=data, meta=_meta())


@router.get(
    "/{instance_id}/steps", response_model=SuccessResponse[list[WorkflowExecutionStepResponse]]
)
async def list_instance_steps(
    instance_id: UUID, steps: ExecutionStepSvc, _caller: CurrentUserId
) -> SuccessResponse[list[WorkflowExecutionStepResponse]]:
    """List every node's own execution result for a workflow instance."""
    records = await steps.list_for_instance(instance_id)
    data = [execution_step_to_response(record) for record in records]
    return SuccessResponse(message="Workflow instance steps retrieved.", data=data, meta=_meta())


@router.get(
    "/{instance_id}/checkpoints", response_model=SuccessResponse[list[WorkflowCheckpointResponse]]
)
async def list_instance_checkpoints(
    instance_id: UUID, checkpoints: CheckpointSvc, _caller: CurrentUserId
) -> SuccessResponse[list[WorkflowCheckpointResponse]]:
    """List every checkpoint recorded for a workflow instance ("Persistent State")."""
    records = await checkpoints.list_for_instance(instance_id)
    data = [checkpoint_to_response(record) for record in records]
    return SuccessResponse(
        message="Workflow instance checkpoints retrieved.", data=data, meta=_meta()
    )


@router.get(
    "/{instance_id}/approvals", response_model=SuccessResponse[list[WorkflowApprovalResponse]]
)
async def list_instance_approvals(
    instance_id: UUID, approvals: ApprovalSvc, _caller: CurrentUserId
) -> SuccessResponse[list[WorkflowApprovalResponse]]:
    """List every human-approval gate recorded for a workflow instance ("Approval History")."""
    records = await approvals.list_for_instance(instance_id)
    data = [approval_to_response(record) for record in records]
    return SuccessResponse(
        message="Workflow instance approvals retrieved.", data=data, meta=_meta()
    )


@router.post(
    "/{instance_id}/approvals/{approval_id}/decide",
    response_model=SuccessResponse[WorkflowApprovalResponse],
)
async def decide_instance_approval(
    instance_id: UUID,
    approval_id: UUID,
    body: WorkflowApprovalDecisionRequest,
    approvals: ApprovalSvc,
    _caller: CurrentUserId,
) -> SuccessResponse[WorkflowApprovalResponse]:
    """Record one approver's own decision for a pending approval gate
    ("Approval Tasks"/"Comments").

    Raises:
        NotFoundError: If no such instance or approval gate exists.
    """
    del instance_id  # scoping context only; approval_id alone identifies the row
    approval = await approvals.decide(
        approval_id, approver=body.approver, approve=body.approve, comments=body.comments
    )
    return SuccessResponse(
        message="Workflow approval decision recorded.",
        data=approval_to_response(approval),
        meta=_meta(),
    )


__all__ = [
    "approval_to_response",
    "checkpoint_to_response",
    "execution_step_to_response",
    "log_to_response",
    "router",
]
