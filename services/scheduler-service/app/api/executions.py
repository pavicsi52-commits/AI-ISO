"""Execution history and log lines."""

from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Query
from shared_core.logging.context import get_log_context

from app.api.deps import ExecutionSvc
from app.models.enums import ExecutionStatus
from app.schemas.response import ResponseMeta, SuccessResponse
from app.schemas.scheduler import ExecutionLogResponse, JobExecutionResponse

router = APIRouter(prefix="/scheduler/executions", tags=["Executions"])


def _meta() -> ResponseMeta:
    """Response metadata carrying this request's id."""
    return ResponseMeta(request_id=get_log_context().request_id or "unknown")


@router.get(
    "", response_model=SuccessResponse[list[JobExecutionResponse]], summary="List executions"
)
async def list_executions(
    organization_id: UUID,
    executions: ExecutionSvc,
    status_filter: Annotated[ExecutionStatus | None, Query(alias="status")] = None,
    job_id: Annotated[UUID | None, Query()] = None,
    limit: Annotated[int, Query(ge=1, le=1_000)] = 200,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> SuccessResponse[list[JobExecutionResponse]]:
    """Executions matching a caller's filters, newest first."""
    rows = await executions.list_filtered(
        organization_id, status=status_filter, job_id=job_id, limit=limit, offset=offset
    )
    return SuccessResponse(
        meta=_meta(),
        data=[JobExecutionResponse.model_validate(one) for one in rows],
        message=f"{len(rows)} execution(s).",
    )


@router.get(
    "/{execution_id}",
    response_model=SuccessResponse[JobExecutionResponse],
    summary="Read one execution",
)
async def get_execution(
    organization_id: UUID, execution_id: UUID, executions: ExecutionSvc
) -> SuccessResponse[JobExecutionResponse]:
    """One execution."""
    found = await executions.get(organization_id, execution_id)
    return SuccessResponse(
        meta=_meta(), data=JobExecutionResponse.model_validate(found), message="Execution read."
    )


@router.get(
    "/{execution_id}/logs",
    response_model=SuccessResponse[list[ExecutionLogResponse]],
    summary="Read one execution's log lines",
)
async def get_execution_logs(
    organization_id: UUID, execution_id: UUID, executions: ExecutionSvc
) -> SuccessResponse[list[ExecutionLogResponse]]:
    """Every log line for one execution, oldest first."""
    rows = await executions.list_logs(organization_id, execution_id)
    return SuccessResponse(
        meta=_meta(),
        data=[ExecutionLogResponse.model_validate(one) for one in rows],
        message=f"{len(rows)} log line(s).",
    )


__all__ = ["router"]
