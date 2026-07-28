"""``/monitoring-collectors``. No REST list entry of its own in
docs/044 -- added directly: "Distributed Collectors" is an explicit
ACCEPTANCE CRITERIA line, and without some way to register a collector
configuration, no metric collection could ever be scheduled at all, the
same "required capability with no REST list entry" precedent applied
throughout this service's own API layer.
"""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter
from shared_core.logging.context import get_log_context

from app.api.deps import CollectorSvc, CurrentUserId
from app.models.monitoring_collector import MonitoringCollector
from app.schemas.collector import MonitoringCollectorCreateRequest, MonitoringCollectorResponse
from app.schemas.response import ResponseMeta, SuccessResponse

router = APIRouter(prefix="/monitoring-collectors", tags=["Monitoring Collectors"])


def _meta() -> ResponseMeta:
    return ResponseMeta(request_id=get_log_context().request_id or "unknown")


def collector_to_response(collector: MonitoringCollector) -> MonitoringCollectorResponse:
    return MonitoringCollectorResponse(
        id=collector.id,
        organization_id=collector.organization_id,
        name=collector.name,
        collector_key=collector.collector_key,
        target_types=collector.target_types,
        parameters=collector.parameters,
        interval_seconds=collector.interval_seconds,
        is_active=collector.is_active,
    )


@router.get("", response_model=SuccessResponse[list[MonitoringCollectorResponse]])
async def list_collectors(
    organization_id: UUID, collectors: CollectorSvc, _caller: CurrentUserId
) -> SuccessResponse[list[MonitoringCollectorResponse]]:
    """List every collector configuration belonging to *organization_id*."""
    records = await collectors.list_for_org(organization_id)
    data = [collector_to_response(record) for record in records]
    return SuccessResponse(message="Monitoring collectors retrieved.", data=data, meta=_meta())


@router.post("", response_model=SuccessResponse[MonitoringCollectorResponse], status_code=201)
async def create_collector(
    body: MonitoringCollectorCreateRequest, collectors: CollectorSvc, _caller: CurrentUserId
) -> SuccessResponse[MonitoringCollectorResponse]:
    """Register a new distributed collector."""
    collector = await collectors.create(
        organization_id=body.organization_id,
        name=body.name,
        collector_key=body.collector_key,
        target_types=body.target_types,
        parameters=body.parameters,
        interval_seconds=body.interval_seconds,
        is_active=body.is_active,
    )
    return SuccessResponse(
        message="Monitoring collector registered.",
        data=collector_to_response(collector),
        meta=_meta(),
    )


__all__ = ["collector_to_response", "router"]
