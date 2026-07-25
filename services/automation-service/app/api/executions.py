"""``/automation/executions``, ``/automation/executions/{id}/logs``,
``/automation/executions/{id}/artifacts``. Per docs/040 REST list.
"""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter
from shared_core.logging.context import get_log_context

from app.api.deps import ArtifactSvc, CurrentUserId, ExecutionLogSvc, ExecutionSvc
from app.api.jobs import execution_to_response
from app.models.automation_artifact import AutomationArtifact
from app.models.automation_execution_log import AutomationExecutionLog
from app.models.enums import ExecutionStatus
from app.schemas.artifact import AutomationArtifactResponse
from app.schemas.execution import AutomationExecutionResponse
from app.schemas.execution_log import AutomationExecutionLogResponse
from app.schemas.response import ResponseMeta, SuccessResponse

router = APIRouter(prefix="/automation/executions", tags=["Automation Executions"])


def _meta() -> ResponseMeta:
    return ResponseMeta(request_id=get_log_context().request_id or "unknown")


def log_to_response(log: AutomationExecutionLog) -> AutomationExecutionLogResponse:
    return AutomationExecutionLogResponse(
        id=log.id,
        execution_id=log.execution_id,
        step_id=log.step_id,
        level=log.level,
        message=log.message,
        metadata=log.metadata_,
        logged_at=log.logged_at,
    )


def artifact_to_response(artifact: AutomationArtifact) -> AutomationArtifactResponse:
    return AutomationArtifactResponse(
        id=artifact.id,
        execution_id=artifact.execution_id,
        artifact_type=artifact.artifact_type,
        name=artifact.name,
        content=artifact.content,
        checksum=artifact.checksum,
    )


@router.get("", response_model=SuccessResponse[list[AutomationExecutionResponse]])
async def list_executions(
    organization_id: UUID,
    executions: ExecutionSvc,
    _caller: CurrentUserId,
    status: ExecutionStatus | None = None,
) -> SuccessResponse[list[AutomationExecutionResponse]]:
    """List every execution in *organization_id*, newest first."""
    records = await executions.list_for_org(organization_id, status=status)
    data = [execution_to_response(record) for record in records]
    return SuccessResponse(message="Automation executions retrieved.", data=data, meta=_meta())


@router.get("/{execution_id}", response_model=SuccessResponse[AutomationExecutionResponse])
async def get_execution(
    execution_id: UUID, executions: ExecutionSvc, _caller: CurrentUserId
) -> SuccessResponse[AutomationExecutionResponse]:
    """Return one automation execution.

    Raises:
        NotFoundError: If no such execution exists.
    """
    execution = await executions.get_by_id(execution_id)
    return SuccessResponse(
        message="Automation execution retrieved.",
        data=execution_to_response(execution),
        meta=_meta(),
    )


@router.get(
    "/{execution_id}/logs", response_model=SuccessResponse[list[AutomationExecutionLogResponse]]
)
async def list_execution_logs(
    execution_id: UUID, logs: ExecutionLogSvc, _caller: CurrentUserId
) -> SuccessResponse[list[AutomationExecutionLogResponse]]:
    """List every log line captured for an execution, oldest first ("Capture")."""
    records = await logs.list_for_execution(execution_id)
    data = [log_to_response(record) for record in records]
    return SuccessResponse(message="Automation execution logs retrieved.", data=data, meta=_meta())


@router.get(
    "/{execution_id}/artifacts",
    response_model=SuccessResponse[list[AutomationArtifactResponse]],
)
async def list_execution_artifacts(
    execution_id: UUID, artifacts: ArtifactSvc, _caller: CurrentUserId
) -> SuccessResponse[list[AutomationArtifactResponse]]:
    """List every artifact stored for an execution ("Store")."""
    records = await artifacts.list_for_execution(execution_id)
    data = [artifact_to_response(record) for record in records]
    return SuccessResponse(
        message="Automation execution artifacts retrieved.", data=data, meta=_meta()
    )


__all__ = ["artifact_to_response", "log_to_response", "router"]
