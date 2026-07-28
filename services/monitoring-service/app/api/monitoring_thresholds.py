"""``GET /monitoring/thresholds``, ``POST /monitoring/thresholds``. Per
docs/044 REST list.
"""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter
from shared_core.logging.context import get_log_context

from app.api.deps import CurrentUserId, ThresholdSvc
from app.models.monitoring_threshold import MonitoringThreshold
from app.schemas.response import ResponseMeta, SuccessResponse
from app.schemas.threshold import MonitoringThresholdCreateRequest, MonitoringThresholdResponse

router = APIRouter(prefix="/monitoring/thresholds", tags=["Monitoring Thresholds"])


def _meta() -> ResponseMeta:
    return ResponseMeta(request_id=get_log_context().request_id or "unknown")


def threshold_to_response(threshold: MonitoringThreshold) -> MonitoringThresholdResponse:
    return MonitoringThresholdResponse(
        id=threshold.id,
        organization_id=threshold.organization_id,
        metric_id=threshold.metric_id,
        threshold_type=threshold.threshold_type,
        informational=threshold.informational,
        low=threshold.low,
        medium=threshold.medium,
        high=threshold.high,
        critical=threshold.critical,
        is_active=threshold.is_active,
    )


@router.get("", response_model=SuccessResponse[list[MonitoringThresholdResponse]])
async def list_thresholds(
    metric_id: UUID, thresholds: ThresholdSvc, _caller: CurrentUserId
) -> SuccessResponse[list[MonitoringThresholdResponse]]:
    """List every active threshold configured for *metric_id*."""
    records = await thresholds.list_for_metric(metric_id)
    data = [threshold_to_response(record) for record in records]
    return SuccessResponse(message="Monitoring thresholds retrieved.", data=data, meta=_meta())


@router.post("", response_model=SuccessResponse[MonitoringThresholdResponse], status_code=201)
async def create_threshold(
    body: MonitoringThresholdCreateRequest, thresholds: ThresholdSvc, _caller: CurrentUserId
) -> SuccessResponse[MonitoringThresholdResponse]:
    """Configure a new threshold."""
    threshold = await thresholds.create(
        organization_id=body.organization_id,
        metric_id=body.metric_id,
        threshold_type=body.threshold_type,
        informational=body.informational,
        low=body.low,
        medium=body.medium,
        high=body.high,
        critical=body.critical,
        is_active=body.is_active,
    )
    return SuccessResponse(
        message="Monitoring threshold created.", data=threshold_to_response(threshold), meta=_meta()
    )


__all__ = ["router", "threshold_to_response"]
