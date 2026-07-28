"""``/monitoring-retention-policies``. No REST list entry of its own in
docs/044 -- added directly: "Retention Policies" is an explicit "TIME
SERIES" "Support" line, and without some way to configure one, every
organization would be stuck on the hardcoded platform default forever.
"""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter
from shared_core.logging.context import get_log_context

from app.api.deps import CurrentUserId, RetentionSvc
from app.models.monitoring_retention import MonitoringRetention
from app.schemas.response import ResponseMeta, SuccessResponse
from app.schemas.retention import MonitoringRetentionCreateRequest, MonitoringRetentionResponse

router = APIRouter(prefix="/monitoring-retention-policies", tags=["Monitoring Retention"])


def _meta() -> ResponseMeta:
    return ResponseMeta(request_id=get_log_context().request_id or "unknown")


def retention_to_response(retention: MonitoringRetention) -> MonitoringRetentionResponse:
    return MonitoringRetentionResponse(
        id=retention.id,
        organization_id=retention.organization_id,
        metric_type=retention.metric_type,
        retention_days=retention.retention_days,
        downsampling_function=retention.downsampling_function,
        downsampling_interval_seconds=retention.downsampling_interval_seconds,
        is_active=retention.is_active,
    )


@router.get("", response_model=SuccessResponse[list[MonitoringRetentionResponse]])
async def list_retention_policies(
    organization_id: UUID, retention: RetentionSvc, _caller: CurrentUserId
) -> SuccessResponse[list[MonitoringRetentionResponse]]:
    """List every retention policy belonging to *organization_id*."""
    records = await retention.list_for_org(organization_id)
    data = [retention_to_response(record) for record in records]
    return SuccessResponse(
        message="Monitoring retention policies retrieved.", data=data, meta=_meta()
    )


@router.post("", response_model=SuccessResponse[MonitoringRetentionResponse], status_code=201)
async def create_retention_policy(
    body: MonitoringRetentionCreateRequest, retention: RetentionSvc, _caller: CurrentUserId
) -> SuccessResponse[MonitoringRetentionResponse]:
    """Configure a new retention/downsampling policy."""
    policy = await retention.create(
        organization_id=body.organization_id,
        metric_type=body.metric_type,
        retention_days=body.retention_days,
        downsampling_function=body.downsampling_function,
        downsampling_interval_seconds=body.downsampling_interval_seconds,
        is_active=body.is_active,
    )
    return SuccessResponse(
        message="Monitoring retention policy created.",
        data=retention_to_response(policy),
        meta=_meta(),
    )


__all__ = ["retention_to_response", "router"]
