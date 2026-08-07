"""Connector registration and lifecycle (docs/058 "CONNECTOR LIFECYCLE", "REST APIs")."""

from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Query
from shared_core.logging.context import get_log_context

from app.api.deps import (
    AuditSvc,
    ConnectionSvc,
    ConnectorSvc,
    CredentialSvc,
    CurrentUserId,
    HealthSvc,
    SyncSvc,
)
from app.models.enums import AuditAction, ConnectorCategory, ConnectorLifecycleStatus
from app.schemas.hub import (
    ConnectionTestResponse,
    ConnectorCategoryResponse,
    ConnectorConfigureRequest,
    ConnectorCreateRequest,
    ConnectorHealthResponse,
    ConnectorInstallRequest,
    ConnectorResponse,
    ConnectorUpgradeRequest,
    ConnectorVersionResponse,
    SyncJobResponse,
    SyncTriggerRequest,
)
from app.schemas.response import ResponseMeta, SuccessResponse

router = APIRouter(prefix="/integrations/connectors", tags=["Connectors"])
categories_router = APIRouter(prefix="/integrations/categories", tags=["Connectors"])


def _meta() -> ResponseMeta:
    return ResponseMeta(request_id=get_log_context().request_id or "unknown")


@router.get("", response_model=SuccessResponse[list[ConnectorResponse]], summary="List connectors")
async def list_connectors(
    organization_id: UUID,
    connectors: ConnectorSvc,
    category: Annotated[ConnectorCategory | None, Query()] = None,
    status_filter: Annotated[ConnectorLifecycleStatus | None, Query(alias="status")] = None,
    limit: Annotated[int, Query(ge=1, le=1_000)] = 200,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> SuccessResponse[list[ConnectorResponse]]:
    """Connectors registered in this organization, newest first."""
    rows = await connectors.list_for_org(
        organization_id, category=category, status=status_filter, limit=limit, offset=offset
    )
    return SuccessResponse(
        message="Connectors listed.",
        data=[ConnectorResponse.model_validate(r) for r in rows],
        meta=_meta(),
    )


@router.get(
    "/{connector_id}", response_model=SuccessResponse[ConnectorResponse], summary="Get a connector"
)
async def get_connector(
    organization_id: UUID, connector_id: UUID, connectors: ConnectorSvc
) -> SuccessResponse[ConnectorResponse]:
    """One connector."""
    found = await connectors.get(organization_id, connector_id)
    return SuccessResponse(
        message="Connector found.", data=ConnectorResponse.model_validate(found), meta=_meta()
    )


@router.post(
    "",
    response_model=SuccessResponse[ConnectorResponse],
    status_code=201,
    summary="Register a connector",
)
async def register_connector(
    organization_id: UUID,
    body: ConnectorCreateRequest,
    connectors: ConnectorSvc,
    audit: AuditSvc,
    caller: CurrentUserId,
) -> SuccessResponse[ConnectorResponse]:
    """Register a new connector instance."""
    created = await connectors.register(
        organization_id,
        name=body.name,
        category=body.category,
        connector_type=body.connector_type,
        auth_method=body.auth_method,
        marketplace_entry_id=body.marketplace_entry_id,
        description=body.description,
        owner_id=body.owner_id,
        tags=body.tags,
    )
    await audit.record(
        organization_id,
        action=AuditAction.CONNECTOR_REGISTERED,
        entity_type="connector",
        entity_id=created.id,
        actor_id=str(caller),
        summary=f"Registered connector {created.name!r}.",
    )
    return SuccessResponse(
        message="Connector registered.",
        data=ConnectorResponse.model_validate(created),
        meta=_meta(),
    )


@router.put(
    "/{connector_id}",
    response_model=SuccessResponse[ConnectorResponse],
    summary="Configure a connector",
)
async def configure_connector(
    organization_id: UUID,
    connector_id: UUID,
    body: ConnectorConfigureRequest,
    connectors: ConnectorSvc,
    audit: AuditSvc,
    caller: CurrentUserId,
) -> SuccessResponse[ConnectorResponse]:
    """Update a connector's own configuration."""
    updated = await connectors.configure(organization_id, connector_id, config=body.config)
    await audit.record(
        organization_id,
        action=AuditAction.CONNECTOR_CONFIGURED,
        entity_type="connector",
        entity_id=connector_id,
        actor_id=str(caller),
        summary=f"Configured connector {updated.name!r}.",
    )
    return SuccessResponse(
        message="Connector configured.",
        data=ConnectorResponse.model_validate(updated),
        meta=_meta(),
    )


@router.delete(
    "/{connector_id}",
    response_model=SuccessResponse[ConnectorResponse],
    summary="Remove a connector",
)
async def remove_connector(
    organization_id: UUID,
    connector_id: UUID,
    connectors: ConnectorSvc,
    audit: AuditSvc,
    caller: CurrentUserId,
) -> SuccessResponse[ConnectorResponse]:
    """Remove a connector -- the lifecycle's own terminal stage."""
    removed = await connectors.remove(organization_id, connector_id)
    await audit.record(
        organization_id,
        action=AuditAction.CONNECTOR_REMOVED,
        entity_type="connector",
        entity_id=connector_id,
        actor_id=str(caller),
        summary=f"Removed connector {removed.name!r}.",
    )
    return SuccessResponse(
        message="Connector removed.", data=ConnectorResponse.model_validate(removed), meta=_meta()
    )


@router.post(
    "/{connector_id}/install",
    response_model=SuccessResponse[ConnectorResponse],
    summary="Install a connector at a given version",
)
async def install_connector(
    organization_id: UUID,
    connector_id: UUID,
    body: ConnectorInstallRequest,
    connectors: ConnectorSvc,
) -> SuccessResponse[ConnectorResponse]:
    """Move a registered connector into ``INSTALLED``."""
    installed = await connectors.install(
        organization_id, connector_id, version_number=body.version_number
    )
    return SuccessResponse(
        message="Connector installed.",
        data=ConnectorResponse.model_validate(installed),
        meta=_meta(),
    )


@router.post(
    "/{connector_id}/test",
    response_model=SuccessResponse[ConnectionTestResponse],
    summary="Test a connection",
)
async def test_connector(
    organization_id: UUID,
    connector_id: UUID,
    connectors: ConnectorSvc,
    credentials: CredentialSvc,
    connections: ConnectionSvc,
) -> SuccessResponse[ConnectionTestResponse]:
    """Attempt to reach a connector's own configured endpoint, and record the outcome."""
    connector = await connectors.get(organization_id, connector_id)
    active_credential = await credentials.get_active_for_connector(connector_id)
    result = await connections.test(
        connector,
        credential_id=active_credential.id if active_credential else None,
        has_active_credential=active_credential is not None,
    )
    if result.status == "success":
        await connectors.mark_validated(organization_id, connector_id)
    return SuccessResponse(
        message="Connection tested.",
        data=ConnectionTestResponse.model_validate(result),
        meta=_meta(),
    )


@router.post(
    "/{connector_id}/enable",
    response_model=SuccessResponse[ConnectorResponse],
    summary="Enable a connector",
)
async def enable_connector(
    organization_id: UUID,
    connector_id: UUID,
    connectors: ConnectorSvc,
    audit: AuditSvc,
    caller: CurrentUserId,
) -> SuccessResponse[ConnectorResponse]:
    """Enable a connector."""
    updated = await connectors.enable(organization_id, connector_id)
    await audit.record(
        organization_id,
        action=AuditAction.CONNECTOR_ENABLED,
        entity_type="connector",
        entity_id=connector_id,
        actor_id=str(caller),
        summary=f"Enabled connector {updated.name!r}.",
    )
    return SuccessResponse(
        message="Connector enabled.", data=ConnectorResponse.model_validate(updated), meta=_meta()
    )


@router.post(
    "/{connector_id}/disable",
    response_model=SuccessResponse[ConnectorResponse],
    summary="Disable a connector",
)
async def disable_connector(
    organization_id: UUID,
    connector_id: UUID,
    connectors: ConnectorSvc,
    audit: AuditSvc,
    caller: CurrentUserId,
) -> SuccessResponse[ConnectorResponse]:
    """Disable a connector."""
    updated = await connectors.disable(organization_id, connector_id)
    await audit.record(
        organization_id,
        action=AuditAction.CONNECTOR_DISABLED,
        entity_type="connector",
        entity_id=connector_id,
        actor_id=str(caller),
        summary=f"Disabled connector {updated.name!r}.",
    )
    return SuccessResponse(
        message="Connector disabled.", data=ConnectorResponse.model_validate(updated), meta=_meta()
    )


@router.post(
    "/{connector_id}/upgrade",
    response_model=SuccessResponse[ConnectorResponse],
    summary="Upgrade a connector",
)
async def upgrade_connector(
    organization_id: UUID,
    connector_id: UUID,
    body: ConnectorUpgradeRequest,
    connectors: ConnectorSvc,
    audit: AuditSvc,
    caller: CurrentUserId,
) -> SuccessResponse[ConnectorResponse]:
    """Move a connector onto a newer version."""
    upgraded = await connectors.upgrade(
        organization_id, connector_id, version_number=body.version_number
    )
    await audit.record(
        organization_id,
        action=AuditAction.CONNECTOR_UPGRADED,
        entity_type="connector",
        entity_id=connector_id,
        actor_id=str(caller),
        summary=f"Upgraded connector {upgraded.name!r} to {body.version_number}.",
    )
    return SuccessResponse(
        message="Connector upgraded.", data=ConnectorResponse.model_validate(upgraded), meta=_meta()
    )


@router.post(
    "/{connector_id}/rollback",
    response_model=SuccessResponse[ConnectorResponse],
    summary="Roll back a connector",
)
async def rollback_connector(
    organization_id: UUID,
    connector_id: UUID,
    body: ConnectorUpgradeRequest,
    connectors: ConnectorSvc,
    audit: AuditSvc,
    caller: CurrentUserId,
) -> SuccessResponse[ConnectorResponse]:
    """Move a connector back onto an older, previously-installed version."""
    rolled_back = await connectors.rollback(
        organization_id, connector_id, version_number=body.version_number
    )
    await audit.record(
        organization_id,
        action=AuditAction.CONNECTOR_ROLLED_BACK,
        entity_type="connector",
        entity_id=connector_id,
        actor_id=str(caller),
        summary=f"Rolled back connector {rolled_back.name!r} to {body.version_number}.",
    )
    return SuccessResponse(
        message="Connector rolled back.",
        data=ConnectorResponse.model_validate(rolled_back),
        meta=_meta(),
    )


@router.post(
    "/{connector_id}/deprecate",
    response_model=SuccessResponse[ConnectorResponse],
    summary="Deprecate a connector",
)
async def deprecate_connector(
    organization_id: UUID, connector_id: UUID, connectors: ConnectorSvc
) -> SuccessResponse[ConnectorResponse]:
    """Mark a connector deprecated."""
    updated = await connectors.deprecate(organization_id, connector_id)
    return SuccessResponse(
        message="Connector deprecated.",
        data=ConnectorResponse.model_validate(updated),
        meta=_meta(),
    )


@router.get(
    "/{connector_id}/versions",
    response_model=SuccessResponse[list[ConnectorVersionResponse]],
    summary="List a connector's own version history",
)
async def list_connector_versions(
    organization_id: UUID, connector_id: UUID, connectors: ConnectorSvc
) -> SuccessResponse[list[ConnectorVersionResponse]]:
    """A connector's own upgrade/rollback history."""
    versions = await connectors.list_versions(organization_id, connector_id)
    return SuccessResponse(
        message="Versions listed.",
        data=[ConnectorVersionResponse.model_validate(v) for v in versions],
        meta=_meta(),
    )


@router.get(
    "/{connector_id}/health",
    response_model=SuccessResponse[list[ConnectorHealthResponse]],
    summary="List a connector's own health-check history",
)
async def list_connector_health(
    organization_id: UUID, connector_id: UUID, connectors: ConnectorSvc, health: HealthSvc
) -> SuccessResponse[list[ConnectorHealthResponse]]:
    """Recent automated health checks for one connector, newest first."""
    await connectors.get(organization_id, connector_id)  # confirms tenant ownership
    rows = await health.list_for_connector(connector_id)
    return SuccessResponse(
        message="Health history listed.",
        data=[ConnectorHealthResponse.model_validate(r) for r in rows],
        meta=_meta(),
    )


@router.post(
    "/{connector_id}/probe",
    response_model=SuccessResponse[ConnectorHealthResponse],
    summary="Run one health probe now",
)
async def probe_connector(
    organization_id: UUID, connector_id: UUID, connectors: ConnectorSvc, health: HealthSvc
) -> SuccessResponse[ConnectorHealthResponse]:
    """Run one on-demand health probe -- the same check the leader-elected sweep runs on its own."""
    connector = await connectors.get(organization_id, connector_id)
    result = await health.probe(connector)
    await connectors.record_health_outcome(connector, succeeded=result.status == "healthy")
    return SuccessResponse(
        message="Health probed.", data=ConnectorHealthResponse.model_validate(result), meta=_meta()
    )


@router.post(
    "/{connector_id}/sync",
    response_model=SuccessResponse[SyncJobResponse],
    summary="Trigger a synchronization run",
)
async def trigger_sync(
    organization_id: UUID,
    connector_id: UUID,
    body: SyncTriggerRequest,
    connectors: ConnectorSvc,
    sync: SyncSvc,
    audit: AuditSvc,
    caller: CurrentUserId,
) -> SuccessResponse[SyncJobResponse]:
    """Queue and immediately run one synchronization job against *body.records*."""
    await connectors.get(organization_id, connector_id)  # confirms tenant ownership
    job = await sync.trigger(
        organization_id,
        connector_id=connector_id,
        mode=body.mode,
        trigger=body.trigger,
        conflict_resolution=body.conflict_resolution,
        triggered_by=str(caller),
    )
    job = await sync.run(organization_id, job, records=body.records)
    await audit.record(
        organization_id,
        action=AuditAction.SYNC_TRIGGERED,
        entity_type="connector",
        entity_id=connector_id,
        actor_id=str(caller),
        summary=f"Triggered a {body.mode!s} sync ({len(body.records)} records).",
    )
    return SuccessResponse(
        message="Synchronization run.", data=SyncJobResponse.model_validate(job), meta=_meta()
    )


@categories_router.get(
    "",
    response_model=SuccessResponse[list[ConnectorCategoryResponse]],
    summary="List connector categories",
)
async def list_categories(
    organization_id: UUID, connectors: ConnectorSvc
) -> SuccessResponse[list[ConnectorCategoryResponse]]:
    """The categories visible in this org, seeding the built-in fifteen on the first call."""
    await connectors.ensure_default_categories(organization_id)
    rows = await connectors.list_categories(organization_id)
    return SuccessResponse(
        message="Categories listed.",
        data=[ConnectorCategoryResponse.model_validate(r) for r in rows],
        meta=_meta(),
    )


__all__ = ["categories_router", "router"]
