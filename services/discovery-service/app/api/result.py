"""``GET /discovery/results``. Per docs/037 REST list."""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter
from shared_core.logging.context import get_log_context

from app.api.deps import CurrentUserId, ResultSvc
from app.models.discovery_result import DiscoveryResult
from app.schemas.response import ResponseMeta, SuccessResponse
from app.schemas.result import DiscoveryResultResponse

router = APIRouter(prefix="/discovery/results", tags=["Results"])


def _meta() -> ResponseMeta:
    return ResponseMeta(request_id=get_log_context().request_id or "unknown")


def _to_response(result: DiscoveryResult) -> DiscoveryResultResponse:
    return DiscoveryResultResponse(
        id=result.id,
        job_id=result.job_id,
        target_id=result.target_id,
        protocol=result.protocol,
        status=result.status,
        latency_ms=result.latency_ms,
        raw_data=result.raw_data,
        error_message=result.error_message,
        executed_at=result.executed_at,
    )


@router.get("", response_model=SuccessResponse[list[DiscoveryResultResponse]])
async def list_results(
    job_id: UUID, results: ResultSvc, _caller: CurrentUserId
) -> SuccessResponse[list[DiscoveryResultResponse]]:
    """List every raw protocol-probe outcome recorded for *job_id*."""
    records = await results.list_for_job(job_id)
    return SuccessResponse(
        message="Discovery results retrieved.",
        data=[_to_response(record) for record in records],
        meta=_meta(),
    )


__all__ = ["router"]
