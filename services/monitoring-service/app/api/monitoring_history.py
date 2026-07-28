"""``/monitoring/history``. No REST list entry of its own in docs/044 --
added directly: ``app/schemas/history.py``'s own
``MonitoringHistoryResponse`` was otherwise never referenced by any
router, and "Availability Trends"/"Failure Trends" (explicit "ANALYTICS"
"Collect" lines) need some way to read the lightweight per-target
historical snapshots :class:`~app.services.history.MonitoringHistoryService`
already records, the same "orphaned schema, found via coverage, wire it
up" precedent ``services/workflow-runtime-service``'s own
``execution_step`` endpoint already established.
"""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter
from shared_core.logging.context import get_log_context

from app.api.deps import CurrentUserId, HistorySvc
from app.models.monitoring_history import MonitoringHistory
from app.schemas.history import MonitoringHistoryResponse
from app.schemas.response import ResponseMeta, SuccessResponse

router = APIRouter(prefix="/monitoring/history", tags=["Monitoring History"])


def _meta() -> ResponseMeta:
    return ResponseMeta(request_id=get_log_context().request_id or "unknown")


def history_to_response(record: MonitoringHistory) -> MonitoringHistoryResponse:
    return MonitoringHistoryResponse(
        id=record.id,
        organization_id=record.organization_id,
        target_id=record.target_id,
        status=record.status,
        score=record.score,
        recorded_at=record.recorded_at,
    )


@router.get("", response_model=SuccessResponse[list[MonitoringHistoryResponse]])
async def list_history(
    history: HistorySvc,
    _caller: CurrentUserId,
    organization_id: UUID | None = None,
    target_id: UUID | None = None,
) -> SuccessResponse[list[MonitoringHistoryResponse]]:
    """List historical health snapshots, filtered by *target_id* or *organization_id*."""
    if target_id is not None:
        records = await history.list_for_target(target_id)
    elif organization_id is not None:
        records = await history.list_for_org(organization_id)
    else:
        records = []
    data = [history_to_response(record) for record in records]
    return SuccessResponse(message="Monitoring history retrieved.", data=data, meta=_meta())


__all__ = ["history_to_response", "router"]
