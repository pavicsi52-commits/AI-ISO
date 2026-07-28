"""``/monitoring-dependencies``. No REST list entry of its own in
docs/044 -- added directly: "Dependency-aware Health" is an explicit
ACCEPTANCE CRITERIA line, and without some way to register a dependency
edge, blast-radius calculation would have no data to walk at all.
"""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter
from shared_core.logging.context import get_log_context

from app.api.deps import CurrentUserId, DependencySvc
from app.models.monitoring_dependency import MonitoringDependency
from app.schemas.dependency import MonitoringDependencyCreateRequest, MonitoringDependencyResponse
from app.schemas.response import ResponseMeta, SuccessResponse

router = APIRouter(prefix="/monitoring-dependencies", tags=["Monitoring Dependencies"])


def _meta() -> ResponseMeta:
    return ResponseMeta(request_id=get_log_context().request_id or "unknown")


def dependency_to_response(dependency: MonitoringDependency) -> MonitoringDependencyResponse:
    return MonitoringDependencyResponse(
        id=dependency.id,
        organization_id=dependency.organization_id,
        parent_target_id=dependency.parent_target_id,
        child_target_id=dependency.child_target_id,
        dependency_type=dependency.dependency_type,
    )


@router.get("", response_model=SuccessResponse[list[MonitoringDependencyResponse]])
async def list_dependency_children(
    parent_target_id: UUID, dependencies: DependencySvc, _caller: CurrentUserId
) -> SuccessResponse[list[MonitoringDependencyResponse]]:
    """List every target that depends on *parent_target_id* ("Blast Radius Calculation")."""
    records = await dependencies.list_children(parent_target_id)
    data = [dependency_to_response(record) for record in records]
    return SuccessResponse(message="Monitoring dependencies retrieved.", data=data, meta=_meta())


@router.post("", response_model=SuccessResponse[MonitoringDependencyResponse], status_code=201)
async def create_dependency(
    body: MonitoringDependencyCreateRequest, dependencies: DependencySvc, _caller: CurrentUserId
) -> SuccessResponse[MonitoringDependencyResponse]:
    """Register a new dependency edge."""
    dependency = await dependencies.create(
        organization_id=body.organization_id,
        parent_target_id=body.parent_target_id,
        child_target_id=body.child_target_id,
        dependency_type=body.dependency_type,
    )
    return SuccessResponse(
        message="Monitoring dependency created.",
        data=dependency_to_response(dependency),
        meta=_meta(),
    )


__all__ = ["dependency_to_response", "router"]
