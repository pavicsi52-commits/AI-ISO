"""``/projects/{id}/settings``. Per docs/034 REST list."""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends
from shared_core.logging.context import get_log_context

from app.api.deps import ProjSvc, SettingsSvc, require_project_admin, require_project_member
from app.models.project_settings import ProjectSettings
from app.schemas.project_settings import ProjectSettingsResponse, ProjectSettingsUpdateRequest
from app.schemas.response import ResponseMeta, SuccessResponse

router = APIRouter(prefix="/projects/{project_id}/settings", tags=["Project Settings"])


def _meta() -> ResponseMeta:
    return ResponseMeta(request_id=get_log_context().request_id or "unknown")


def _to_response(settings: ProjectSettings) -> ProjectSettingsResponse:
    return ProjectSettingsResponse(
        id=settings.id,
        project_id=settings.project_id,
        default_environment=settings.default_environment,
        default_connector_id=settings.default_connector_id,
        default_workflow_runtime=settings.default_workflow_runtime,
        notification_settings=settings.notification_settings,
        retention_policies=settings.retention_policies,
        execution_policies=settings.execution_policies,
        automation_policies=settings.automation_policies,
        validation_policies=settings.validation_policies,
        monitoring_policies=settings.monitoring_policies,
        ai_settings=settings.ai_settings,
        storage_policies=settings.storage_policies,
        security_policies=settings.security_policies,
        created_at=settings.created_at,
        updated_at=settings.updated_at,
    )


@router.get(
    "",
    response_model=SuccessResponse[ProjectSettingsResponse],
    dependencies=[Depends(require_project_member)],
)
async def get_settings(
    project_id: UUID, projects: ProjSvc, settings: SettingsSvc
) -> SuccessResponse[ProjectSettingsResponse]:
    """Return a project's settings, creating defaults if missing."""
    project = await projects.get_by_id(project_id)
    record = await settings.get_or_create(project_id, organization_id=project.organization_id)
    return SuccessResponse(message="Settings retrieved.", data=_to_response(record), meta=_meta())


@router.put(
    "",
    response_model=SuccessResponse[ProjectSettingsResponse],
    dependencies=[Depends(require_project_admin)],
)
async def update_settings(
    project_id: UUID, body: ProjectSettingsUpdateRequest, projects: ProjSvc, settings: SettingsSvc
) -> SuccessResponse[ProjectSettingsResponse]:
    """Update a project's settings ("Settings Updates")."""
    project = await projects.get_by_id(project_id)
    record = await settings.update(
        project_id,
        organization_id=project.organization_id,
        default_environment=body.default_environment,
        default_connector_id=body.default_connector_id,
        default_workflow_runtime=body.default_workflow_runtime,
        notification_settings=body.notification_settings,
        retention_policies=body.retention_policies,
        execution_policies=body.execution_policies,
        automation_policies=body.automation_policies,
        validation_policies=body.validation_policies,
        monitoring_policies=body.monitoring_policies,
        ai_settings=body.ai_settings,
        storage_policies=body.storage_policies,
        security_policies=body.security_policies,
    )
    return SuccessResponse(message="Settings updated.", data=_to_response(record), meta=_meta())


__all__ = ["router"]
