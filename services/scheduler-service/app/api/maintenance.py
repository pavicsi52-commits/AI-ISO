"""Maintenance windows."""

from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Query, status
from shared_core.logging.context import get_log_context

from app.api.deps import AuditSvc, CurrentUserId, MaintenanceSvc
from app.models.enums import AuditAction
from app.schemas.response import ResponseMeta, SuccessResponse
from app.schemas.scheduler import MaintenanceWindowCreateRequest, MaintenanceWindowResponse

router = APIRouter(prefix="/scheduler/maintenance", tags=["Maintenance"])


def _meta() -> ResponseMeta:
    """Response metadata carrying this request's id."""
    return ResponseMeta(request_id=get_log_context().request_id or "unknown")


@router.post(
    "",
    response_model=SuccessResponse[MaintenanceWindowResponse],
    status_code=status.HTTP_201_CREATED,
    summary="Define a maintenance window",
)
async def create_window(
    organization_id: UUID,
    body: MaintenanceWindowCreateRequest,
    maintenance: MaintenanceSvc,
    audit: AuditSvc,
    caller: CurrentUserId,
) -> SuccessResponse[MaintenanceWindowResponse]:
    """Define a maintenance window."""
    created = await maintenance.create_window(
        organization_id,
        title=body.title,
        starts_at=body.starts_at,
        ends_at=body.ends_at,
        scope=body.scope,
        scope_id=body.scope_id,
        kind=body.kind,
        description=body.description,
        timezone=body.timezone,
        recurrence=body.recurrence,
        recurrence_until=body.recurrence_until,
        allow_critical_override=body.allow_critical_override,
    )
    await audit.record(
        organization_id,
        action=AuditAction.MAINTENANCE_WINDOW_CREATED,
        entity_type="maintenance_window",
        entity_id=created.id,
        entity_reference=created.title,
        actor_id=str(caller),
        summary=f"Created maintenance window {created.title!r}.",
    )
    return SuccessResponse(
        meta=_meta(),
        data=MaintenanceWindowResponse.model_validate(created),
        message="Maintenance window created.",
    )


@router.get(
    "",
    response_model=SuccessResponse[list[MaintenanceWindowResponse]],
    summary="List maintenance windows",
)
async def list_windows(
    organization_id: UUID,
    maintenance: MaintenanceSvc,
    limit: Annotated[int, Query(ge=1, le=1_000)] = 200,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> SuccessResponse[list[MaintenanceWindowResponse]]:
    """Every window this organization has defined, soonest first."""
    rows = await maintenance.list_windows(organization_id, limit=limit, offset=offset)
    return SuccessResponse(
        meta=_meta(),
        data=[MaintenanceWindowResponse.model_validate(one) for one in rows],
        message=f"{len(rows)} window(s).",
    )


@router.get(
    "/active",
    response_model=SuccessResponse[list[MaintenanceWindowResponse]],
    summary="List currently-active maintenance windows",
)
async def list_active_windows(
    organization_id: UUID, maintenance: MaintenanceSvc
) -> SuccessResponse[list[MaintenanceWindowResponse]]:
    """Every window active right now."""
    rows = await maintenance.active_windows(organization_id)
    return SuccessResponse(
        meta=_meta(),
        data=[MaintenanceWindowResponse.model_validate(one) for one in rows],
        message=f"{len(rows)} active window(s).",
    )


@router.get(
    "/{window_id}",
    response_model=SuccessResponse[MaintenanceWindowResponse],
    summary="Read one maintenance window",
)
async def get_window(
    organization_id: UUID, window_id: UUID, maintenance: MaintenanceSvc
) -> SuccessResponse[MaintenanceWindowResponse]:
    """One maintenance window."""
    found = await maintenance.get(organization_id, window_id)
    return SuccessResponse(
        meta=_meta(),
        data=MaintenanceWindowResponse.model_validate(found),
        message="Maintenance window read.",
    )


__all__ = ["router"]
