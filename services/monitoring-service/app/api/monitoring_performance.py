"""``GET /monitoring/performance``. Per docs/044 REST list. A computed
view, not a table -- see :mod:`app.schemas.performance`'s own docstring.
"""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from fastapi import APIRouter
from shared_core.logging.context import get_log_context

from app.api.deps import CurrentUserId, PerformanceSvc
from app.schemas.performance import (
    MonitoringPerformanceMetricSummary,
    MonitoringPerformanceResponse,
)
from app.schemas.response import ResponseMeta, SuccessResponse

router = APIRouter(prefix="/monitoring/performance", tags=["Monitoring Performance"])


def _meta() -> ResponseMeta:
    return ResponseMeta(request_id=get_log_context().request_id or "unknown")


@router.get("", response_model=SuccessResponse[MonitoringPerformanceResponse])
async def get_performance(
    target_id: UUID,
    performance: PerformanceSvc,
    _caller: CurrentUserId,
    since: datetime | None = None,
) -> SuccessResponse[MonitoringPerformanceResponse]:
    """Return *target_id*'s own performance summary over a window."""
    summaries = await performance.summarize_for_target(target_id, since=since)
    data = MonitoringPerformanceResponse(
        target_id=target_id,
        metrics=[MonitoringPerformanceMetricSummary(**summary) for summary in summaries],
    )
    return SuccessResponse(message="Monitoring performance retrieved.", data=data, meta=_meta())


__all__ = ["router"]
