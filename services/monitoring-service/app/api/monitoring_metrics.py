"""``GET /monitoring/metrics``, ``GET /monitoring/metrics/{id}``. Per
docs/044 REST list. ``POST /monitoring/metrics`` and
``GET /monitoring/metrics/{id}/series`` have no REST list entry of
their own -- added directly: without a create endpoint there is no way
to define a metric at all, and without a series endpoint "Historical
Queries"/"Time-window Analysis" (both explicit "TIME SERIES" "Support"
lines) would have no REST surface, the same "required capability with
no REST list entry" precedent ``services/validation-service``'s own
catalog endpoints already established.
"""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from fastapi import APIRouter
from shared_core.logging.context import get_log_context

from app.api.deps import CurrentUserId, MetricSeriesSvc, MetricSvc
from app.models.monitoring_metric import MonitoringMetric
from app.models.monitoring_metric_series import MonitoringMetricSeries
from app.schemas.metric import MonitoringMetricCreateRequest, MonitoringMetricResponse
from app.schemas.metric_series import MonitoringMetricSeriesResponse
from app.schemas.response import ResponseMeta, SuccessResponse

router = APIRouter(prefix="/monitoring/metrics", tags=["Monitoring Metrics"])


def _meta() -> ResponseMeta:
    return ResponseMeta(request_id=get_log_context().request_id or "unknown")


def metric_to_response(metric: MonitoringMetric) -> MonitoringMetricResponse:
    return MonitoringMetricResponse(
        id=metric.id,
        organization_id=metric.organization_id,
        collector_id=metric.collector_id,
        metric_type=metric.metric_type,
        name=metric.name,
        unit=metric.unit,
    )


def series_to_response(point: MonitoringMetricSeries) -> MonitoringMetricSeriesResponse:
    return MonitoringMetricSeriesResponse(
        id=point.id,
        organization_id=point.organization_id,
        metric_id=point.metric_id,
        target_id=point.target_id,
        value=point.value,
        tags=point.tags,
        recorded_at=point.recorded_at,
    )


@router.get("", response_model=SuccessResponse[list[MonitoringMetricResponse]])
async def list_metrics(
    organization_id: UUID, metrics: MetricSvc, _caller: CurrentUserId
) -> SuccessResponse[list[MonitoringMetricResponse]]:
    """List every reusable metric definition in *organization_id*."""
    records = await metrics.list_for_org(organization_id)
    data = [metric_to_response(record) for record in records]
    return SuccessResponse(message="Monitoring metrics retrieved.", data=data, meta=_meta())


@router.post("", response_model=SuccessResponse[MonitoringMetricResponse], status_code=201)
async def create_metric(
    body: MonitoringMetricCreateRequest, metrics: MetricSvc, _caller: CurrentUserId
) -> SuccessResponse[MonitoringMetricResponse]:
    """Define a new reusable metric."""
    metric = await metrics.create(
        organization_id=body.organization_id,
        collector_id=body.collector_id,
        metric_type=body.metric_type,
        name=body.name,
        unit=body.unit,
    )
    return SuccessResponse(
        message="Monitoring metric defined.", data=metric_to_response(metric), meta=_meta()
    )


@router.get("/{metric_id}", response_model=SuccessResponse[MonitoringMetricResponse])
async def get_metric(
    metric_id: UUID, metrics: MetricSvc, _caller: CurrentUserId
) -> SuccessResponse[MonitoringMetricResponse]:
    """Return one metric definition.

    Raises:
        NotFoundError: If no such metric exists.
    """
    metric = await metrics.get_by_id(metric_id)
    return SuccessResponse(
        message="Monitoring metric retrieved.", data=metric_to_response(metric), meta=_meta()
    )


@router.get(
    "/{metric_id}/series", response_model=SuccessResponse[list[MonitoringMetricSeriesResponse]]
)
async def get_metric_series(
    metric_id: UUID,
    target_id: UUID,
    series: MetricSeriesSvc,
    _caller: CurrentUserId,
    since: datetime | None = None,
) -> SuccessResponse[list[MonitoringMetricSeriesResponse]]:
    """Return *metric_id*'s own recorded data points for *target_id*
    ("Historical Queries", "Time-window Analysis").
    """
    records = await series.list_for_target(target_id, metric_id=metric_id, since=since)
    data = [series_to_response(record) for record in records]
    return SuccessResponse(message="Metric series retrieved.", data=data, meta=_meta())


__all__ = ["metric_to_response", "router", "series_to_response"]
