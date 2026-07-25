"""``/assets/{id}/maintenance``. Per docs/038 REST list."""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter
from shared_core.logging.context import get_log_context

from app.api.deps import CurrentUserId, MaintenanceSvc
from app.models.asset_maintenance import AssetMaintenance
from app.schemas.maintenance import AssetMaintenanceCreateRequest, AssetMaintenanceResponse
from app.schemas.response import ResponseMeta, SuccessResponse

router = APIRouter(prefix="/assets", tags=["Maintenance"])


def _meta() -> ResponseMeta:
    return ResponseMeta(request_id=get_log_context().request_id or "unknown")


def maintenance_to_response(maintenance: AssetMaintenance) -> AssetMaintenanceResponse:
    return AssetMaintenanceResponse(
        id=maintenance.id,
        managed_asset_id=maintenance.managed_asset_id,
        maintenance_type=maintenance.maintenance_type,
        status=maintenance.status,
        description=maintenance.description,
        scheduled_at=maintenance.scheduled_at,
        completed_at=maintenance.completed_at,
        approved_by=maintenance.approved_by,
        approved_at=maintenance.approved_at,
    )


@router.get(
    "/{managed_asset_id}/maintenance",
    response_model=SuccessResponse[list[AssetMaintenanceResponse]],
)
async def list_maintenance(
    managed_asset_id: UUID, maintenance: MaintenanceSvc, _caller: CurrentUserId
) -> SuccessResponse[list[AssetMaintenanceResponse]]:
    """List every maintenance activity for a managed asset ("Maintenance Calendar")."""
    records = await maintenance.list_for_managed_asset(managed_asset_id)
    data = [maintenance_to_response(record) for record in records]
    return SuccessResponse(message="Maintenance activities retrieved.", data=data, meta=_meta())


@router.post(
    "/{managed_asset_id}/maintenance",
    response_model=SuccessResponse[AssetMaintenanceResponse],
    status_code=201,
)
async def schedule_maintenance(
    managed_asset_id: UUID,
    body: AssetMaintenanceCreateRequest,
    maintenance: MaintenanceSvc,
    _caller: CurrentUserId,
    organization_id: UUID,
) -> SuccessResponse[AssetMaintenanceResponse]:
    """Schedule a maintenance activity ("Scheduled"/"Emergency"/"Preventive"/"Corrective")."""
    record = await maintenance.schedule(
        managed_asset_id,
        organization_id=organization_id,
        maintenance_type=body.maintenance_type,
        description=body.description,
        scheduled_at=body.scheduled_at,
    )
    return SuccessResponse(
        message="Maintenance scheduled.", data=maintenance_to_response(record), meta=_meta()
    )


__all__ = ["maintenance_to_response", "router"]
