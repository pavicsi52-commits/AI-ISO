"""``/maintenance-windows`` -- scheduled/recurring/emergency windows."""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter
from shared_core.logging.context import get_log_context

from app.api.deps import CurrentUserId, MaintenanceWindowSvc
from app.models.alert_maintenance_window import AlertMaintenanceWindow
from app.schemas.maintenance_window import (
    MaintenanceWindowCreateRequest,
    MaintenanceWindowResponse,
)
from app.schemas.response import ResponseMeta, SuccessResponse

router = APIRouter(prefix="/maintenance-windows", tags=["Maintenance Windows"])


def _meta() -> ResponseMeta:
    return ResponseMeta(request_id=get_log_context().request_id or "unknown")


def window_to_response(window: AlertMaintenanceWindow) -> MaintenanceWindowResponse:
    """Map an :class:`AlertMaintenanceWindow` row onto its own response schema."""
    return MaintenanceWindowResponse(
        id=window.id,
        organization_id=window.organization_id,
        project_id=window.project_id,
        name=window.name,
        window_type=window.window_type,
        scope=window.scope,
        scope_reference=window.scope_reference,
        recurrence_rule=window.recurrence_rule,
        starts_at=window.starts_at,
        ends_at=window.ends_at,
        enabled=window.enabled,
    )


@router.get("", response_model=SuccessResponse[list[MaintenanceWindowResponse]])
async def list_maintenance_windows(
    organization_id: UUID,
    windows: MaintenanceWindowSvc,
    _caller: CurrentUserId,
    active_only: bool = False,
) -> SuccessResponse[list[MaintenanceWindowResponse]]:
    """List maintenance windows.

    ``active_only=true`` returns only those genuinely in force right
    now, recurrence evaluated -- a stored ``RECURRING`` window's own
    interval is just its first occurrence, so a plain date filter would
    answer this wrong.
    """
    records = (
        await windows.list_active(organization_id)
        if active_only
        else await windows.list_for_org(organization_id)
    )
    data = [window_to_response(record) for record in records]
    return SuccessResponse(message="Maintenance windows retrieved.", data=data, meta=_meta())


@router.post("", response_model=SuccessResponse[MaintenanceWindowResponse], status_code=201)
async def create_maintenance_window(
    body: MaintenanceWindowCreateRequest,
    windows: MaintenanceWindowSvc,
    _caller: CurrentUserId,
) -> SuccessResponse[MaintenanceWindowResponse]:
    """Create a maintenance window."""
    window = await windows.create(
        organization_id=body.organization_id,
        project_id=body.project_id,
        name=body.name,
        window_type=body.window_type,
        scope=body.scope,
        scope_reference=body.scope_reference,
        recurrence_rule=body.recurrence_rule,
        starts_at=body.starts_at,
        ends_at=body.ends_at,
        enabled=body.enabled,
    )
    return SuccessResponse(
        message="Maintenance window created.", data=window_to_response(window), meta=_meta()
    )


__all__ = ["router", "window_to_response"]
