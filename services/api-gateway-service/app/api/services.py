"""Backend service registration and version management (docs/056 "REST APIs")."""

from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Query, status
from shared_core.logging.context import get_log_context

from app.api.deps import AuditSvc, CurrentUserId, ServiceRegistrySvc, VersionSvc
from app.models.enums import AuditAction
from app.schemas.gateway import (
    ServiceCreateRequest,
    ServiceResponse,
    ServiceUpdateRequest,
    VersionCreateRequest,
    VersionDeprecateRequest,
    VersionResponse,
)
from app.schemas.response import ResponseMeta, SuccessResponse

router = APIRouter(prefix="/gateway/services", tags=["Services"])


def _meta() -> ResponseMeta:
    return ResponseMeta(request_id=get_log_context().request_id or "unknown")


@router.get(
    "", response_model=SuccessResponse[list[ServiceResponse]], summary="List backend services"
)
async def list_services(
    organization_id: UUID,
    services: ServiceRegistrySvc,
    enabled: Annotated[bool | None, Query()] = None,
) -> SuccessResponse[list[ServiceResponse]]:
    """Services registered in this organization."""
    rows = await services.list_services(organization_id, enabled=enabled)
    return SuccessResponse(
        message="Services listed.",
        data=[ServiceResponse.model_validate(r) for r in rows],
        meta=_meta(),
    )


@router.get(
    "/{service_id}",
    response_model=SuccessResponse[ServiceResponse],
    summary="Get a backend service",
)
async def get_service(
    organization_id: UUID, service_id: UUID, services: ServiceRegistrySvc
) -> SuccessResponse[ServiceResponse]:
    """One registered service."""
    found = await services.get(organization_id, service_id)
    return SuccessResponse(
        message="Service found.", data=ServiceResponse.model_validate(found), meta=_meta()
    )


@router.post(
    "",
    response_model=SuccessResponse[ServiceResponse],
    status_code=status.HTTP_201_CREATED,
    summary="Register a backend service",
)
async def create_service(
    organization_id: UUID,
    body: ServiceCreateRequest,
    services: ServiceRegistrySvc,
    audit: AuditSvc,
    caller: CurrentUserId,
) -> SuccessResponse[ServiceResponse]:
    """Register a new backend service."""
    created = await services.register(
        organization_id,
        name=body.name,
        instances=[instance.model_dump() for instance in body.instances],
        description=body.description,
        load_balancing_strategy=body.load_balancing_strategy,
        health_check_path=body.health_check_path,
        timeout_seconds=body.timeout_seconds,
        circuit_breaker_enabled=body.circuit_breaker_enabled,
        actor_id=str(caller),
    )
    await audit.record(
        organization_id,
        action=AuditAction.SERVICE_REGISTERED,
        entity_type="service",
        entity_id=created.id,
        actor_id=str(caller),
        summary=f"Registered service {created.name!r}.",
    )
    return SuccessResponse(
        message="Service registered.", data=ServiceResponse.model_validate(created), meta=_meta()
    )


@router.put(
    "/{service_id}",
    response_model=SuccessResponse[ServiceResponse],
    summary="Update a backend service",
)
async def update_service(
    organization_id: UUID,
    service_id: UUID,
    body: ServiceUpdateRequest,
    services: ServiceRegistrySvc,
    audit: AuditSvc,
    caller: CurrentUserId,
) -> SuccessResponse[ServiceResponse]:
    """Edit a service's editable fields."""
    fields = body.model_dump(exclude_unset=True)
    if "instances" in fields and fields["instances"] is not None:
        fields["instances"] = [dict(instance) for instance in fields["instances"]]
    updated = await services.update(organization_id, service_id, actor_id=str(caller), **fields)
    await audit.record(
        organization_id,
        action=AuditAction.SERVICE_UPDATED,
        entity_type="service",
        entity_id=updated.id,
        actor_id=str(caller),
        summary=f"Updated service {updated.name!r}.",
    )
    return SuccessResponse(
        message="Service updated.", data=ServiceResponse.model_validate(updated), meta=_meta()
    )


@router.delete(
    "/{service_id}", status_code=status.HTTP_204_NO_CONTENT, summary="Deregister a backend service"
)
async def delete_service(
    organization_id: UUID, service_id: UUID, services: ServiceRegistrySvc, caller: CurrentUserId
) -> None:
    """Deregister a service."""
    await services.delete(organization_id, service_id, actor_id=str(caller))


@router.get(
    "/{service_id}/versions",
    response_model=SuccessResponse[list[VersionResponse]],
    summary="List a service's own versions",
)
async def list_versions(
    organization_id: UUID, service_id: UUID, versions: VersionSvc
) -> SuccessResponse[list[VersionResponse]]:
    """Every version registered for one service."""
    rows = await versions.list_for_service(organization_id, service_id)
    return SuccessResponse(
        message="Versions listed.",
        data=[VersionResponse.model_validate(r) for r in rows],
        meta=_meta(),
    )


@router.post(
    "/{service_id}/versions",
    response_model=SuccessResponse[VersionResponse],
    status_code=status.HTTP_201_CREATED,
    summary="Register a service version",
)
async def create_version(
    organization_id: UUID, service_id: UUID, body: VersionCreateRequest, versions: VersionSvc
) -> SuccessResponse[VersionResponse]:
    """Register a new version for one service."""
    created = await versions.register(
        organization_id, service_id=service_id, version=body.version, is_default=body.is_default
    )
    return SuccessResponse(
        message="Version registered.", data=VersionResponse.model_validate(created), meta=_meta()
    )


@router.post(
    "/{service_id}/versions/{version_id}/deprecate",
    response_model=SuccessResponse[VersionResponse],
    summary="Deprecate a service version",
)
async def deprecate_version(
    organization_id: UUID,
    service_id: UUID,
    version_id: UUID,
    body: VersionDeprecateRequest,
    versions: VersionSvc,
) -> SuccessResponse[VersionResponse]:
    """Mark a version deprecated, with optional guidance and a sunset date."""
    updated = await versions.deprecate(
        organization_id, version_id, message=body.message, sunset_at=body.sunset_at
    )
    return SuccessResponse(
        message="Version deprecated.", data=VersionResponse.model_validate(updated), meta=_meta()
    )


__all__ = ["router"]
