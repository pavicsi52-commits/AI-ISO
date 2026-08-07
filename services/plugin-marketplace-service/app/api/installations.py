"""Installation-id-addressed extensions to the plugin lifecycle: listing every
installation directly, configuration, removal, permission grants, and
health history (docs/059 "INSTALLATION MANAGEMENT" / "PERMISSION MODEL"
/ "HEALTH MONITORING", extension surface beyond the fifteen literal
``/plugins/{id}/...`` endpoints, which only address *the* installation
implied by a single plugin id).
"""

from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Query
from shared_core.logging.context import get_log_context

from app.api.deps import AuditSvc, CurrentUserId, HealthSvc, InstallationSvc, PermissionSvc
from app.models.enums import AuditAction, PluginInstallationStatus
from app.schemas.marketplace import (
    PluginConfigureRequest,
    PluginHealthResponse,
    PluginInstallationResponse,
    PluginPermissionDecisionRequest,
    PluginPermissionRequestRequest,
    PluginPermissionResponse,
)
from app.schemas.response import ResponseMeta, SuccessResponse

router = APIRouter(prefix="/plugins/installations", tags=["Installations"])


def _meta() -> ResponseMeta:
    return ResponseMeta(request_id=get_log_context().request_id or "unknown")


@router.get(
    "",
    response_model=SuccessResponse[list[PluginInstallationResponse]],
    summary="List installations",
)
async def list_installations(
    organization_id: UUID,
    installations: InstallationSvc,
    status_filter: Annotated[PluginInstallationStatus | None, Query(alias="status")] = None,
    limit: Annotated[int, Query(ge=1, le=1_000)] = 200,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> SuccessResponse[list[PluginInstallationResponse]]:
    """This organization's own installations, newest first."""
    rows = await installations.list_for_org(
        organization_id, status=status_filter, limit=limit, offset=offset
    )
    return SuccessResponse(
        message="Installations listed.",
        data=[PluginInstallationResponse.model_validate(r) for r in rows],
        meta=_meta(),
    )


@router.get(
    "/{installation_id}",
    response_model=SuccessResponse[PluginInstallationResponse],
    summary="Get an installation",
)
async def get_installation(
    organization_id: UUID, installation_id: UUID, installations: InstallationSvc
) -> SuccessResponse[PluginInstallationResponse]:
    """One installation."""
    found = await installations.get(organization_id, installation_id)
    return SuccessResponse(
        message="Installation found.",
        data=PluginInstallationResponse.model_validate(found),
        meta=_meta(),
    )


@router.put(
    "/{installation_id}/configuration",
    response_model=SuccessResponse[PluginInstallationResponse],
    summary="Configure an installation",
)
async def configure_installation(
    organization_id: UUID,
    installation_id: UUID,
    body: PluginConfigureRequest,
    installations: InstallationSvc,
) -> SuccessResponse[PluginInstallationResponse]:
    """Update an installation's own configuration."""
    updated = await installations.configure(
        organization_id, installation_id, configuration=body.configuration
    )
    return SuccessResponse(
        message="Installation configured.",
        data=PluginInstallationResponse.model_validate(updated),
        meta=_meta(),
    )


@router.delete(
    "/{installation_id}",
    response_model=SuccessResponse[PluginInstallationResponse],
    summary="Remove an installation",
)
async def remove_installation(
    organization_id: UUID,
    installation_id: UUID,
    installations: InstallationSvc,
    audit: AuditSvc,
    caller: CurrentUserId,
) -> SuccessResponse[PluginInstallationResponse]:
    """Remove an installation -- the lifecycle's own terminal stage."""
    removed = await installations.remove(organization_id, installation_id)
    await audit.record(
        organization_id,
        action=AuditAction.PLUGIN_REMOVED,
        entity_type="plugin_installation",
        entity_id=installation_id,
        actor_id=str(caller),
        summary=f"Removed installation {installation_id}.",
    )
    return SuccessResponse(
        message="Installation removed.",
        data=PluginInstallationResponse.model_validate(removed),
        meta=_meta(),
    )


@router.get(
    "/{installation_id}/permissions",
    response_model=SuccessResponse[list[PluginPermissionResponse]],
    summary="List permission grants",
)
async def list_permissions(
    installation_id: UUID, permissions: PermissionSvc
) -> SuccessResponse[list[PluginPermissionResponse]]:
    """Every capability grant requested for one installation."""
    rows = await permissions.list_for_installation(installation_id)
    return SuccessResponse(
        message="Permissions listed.",
        data=[PluginPermissionResponse.model_validate(r) for r in rows],
        meta=_meta(),
    )


@router.post(
    "/{installation_id}/permissions",
    response_model=SuccessResponse[PluginPermissionResponse],
    status_code=201,
    summary="Request a permission",
)
async def request_permission(
    organization_id: UUID,
    installation_id: UUID,
    body: PluginPermissionRequestRequest,
    permissions: PermissionSvc,
) -> SuccessResponse[PluginPermissionResponse]:
    """Request one capability for an installation."""
    created = await permissions.request(
        organization_id,
        installation_id,
        category=body.category,
        scope=body.scope,
        justification=body.justification,
    )
    return SuccessResponse(
        message="Permission requested.",
        data=PluginPermissionResponse.model_validate(created),
        meta=_meta(),
    )


@router.post(
    "/permissions/{grant_id}/grant",
    response_model=SuccessResponse[PluginPermissionResponse],
    summary="Grant a permission",
)
async def grant_permission(
    grant_id: UUID, body: PluginPermissionDecisionRequest, permissions: PermissionSvc
) -> SuccessResponse[PluginPermissionResponse]:
    """Grant a pending capability request."""
    updated = await permissions.grant(grant_id, decided_by=body.decided_by)
    return SuccessResponse(
        message="Permission granted.",
        data=PluginPermissionResponse.model_validate(updated),
        meta=_meta(),
    )


@router.post(
    "/permissions/{grant_id}/deny",
    response_model=SuccessResponse[PluginPermissionResponse],
    summary="Deny a permission",
)
async def deny_permission(
    grant_id: UUID, body: PluginPermissionDecisionRequest, permissions: PermissionSvc
) -> SuccessResponse[PluginPermissionResponse]:
    """Deny a pending capability request."""
    updated = await permissions.deny(grant_id, decided_by=body.decided_by)
    return SuccessResponse(
        message="Permission denied.",
        data=PluginPermissionResponse.model_validate(updated),
        meta=_meta(),
    )


@router.post(
    "/permissions/{grant_id}/revoke",
    response_model=SuccessResponse[PluginPermissionResponse],
    summary="Revoke a permission",
)
async def revoke_permission(
    grant_id: UUID, body: PluginPermissionDecisionRequest, permissions: PermissionSvc
) -> SuccessResponse[PluginPermissionResponse]:
    """Revoke a previously granted capability."""
    updated = await permissions.revoke(grant_id, decided_by=body.decided_by)
    return SuccessResponse(
        message="Permission revoked.",
        data=PluginPermissionResponse.model_validate(updated),
        meta=_meta(),
    )


@router.get(
    "/{installation_id}/health",
    response_model=SuccessResponse[list[PluginHealthResponse]],
    summary="List health-check history",
)
async def list_health(
    installation_id: UUID, health: HealthSvc
) -> SuccessResponse[list[PluginHealthResponse]]:
    """Recent automated health checks for one installation, newest first."""
    rows = await health.list_for_installation(installation_id)
    return SuccessResponse(
        message="Health history listed.",
        data=[PluginHealthResponse.model_validate(r) for r in rows],
        meta=_meta(),
    )


@router.post(
    "/{installation_id}/health/probe",
    response_model=SuccessResponse[PluginHealthResponse],
    summary="Run one health probe now",
)
async def probe_installation(
    organization_id: UUID, installation_id: UUID, installations: InstallationSvc, health: HealthSvc
) -> SuccessResponse[PluginHealthResponse]:
    """Run one on-demand health probe -- the same check the leader-elected sweep runs on its own."""
    installation = await installations.get(organization_id, installation_id)
    result = await health.probe(installation)
    return SuccessResponse(
        message="Health probed.", data=PluginHealthResponse.model_validate(result), meta=_meta()
    )


__all__ = ["router"]
