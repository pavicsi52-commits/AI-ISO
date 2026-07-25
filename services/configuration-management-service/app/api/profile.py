"""``/configurations``, ``/configurations/{id}/versions``,
``/configurations/{id}/rollback``, ``/configurations/{id}/backup``,
``/configurations/{id}/restore``. Per docs/039 REST list.
"""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter
from shared_core.logging.context import get_log_context

from app.api.deps import (
    BackupSvc,
    CurrentUserId,
    ProfileSvc,
    RestoreSvc,
    RollbackSvc,
    VersionSvc,
)
from app.models.configuration_backup import ConfigurationBackup
from app.models.configuration_profile import ConfigurationProfile
from app.models.configuration_restore_job import ConfigurationRestoreJob
from app.models.configuration_rollback import ConfigurationRollback
from app.models.configuration_version import ConfigurationVersion
from app.schemas.backup import ConfigurationBackupCreateRequest, ConfigurationBackupResponse
from app.schemas.profile import (
    ConfigurationProfileCreateRequest,
    ConfigurationProfilePatchRequest,
    ConfigurationProfileResponse,
    ConfigurationProfileUpdateRequest,
)
from app.schemas.response import ResponseMeta, SuccessResponse
from app.schemas.restore import ConfigurationRestoreCreateRequest, ConfigurationRestoreJobResponse
from app.schemas.rollback import ConfigurationRollbackCreateRequest, ConfigurationRollbackResponse
from app.schemas.version import ConfigurationVersionResponse

router = APIRouter(prefix="/configurations", tags=["Configuration Profiles"])


def _meta() -> ResponseMeta:
    return ResponseMeta(request_id=get_log_context().request_id or "unknown")


def profile_to_response(profile: ConfigurationProfile) -> ConfigurationProfileResponse:
    return ConfigurationProfileResponse(
        id=profile.id,
        organization_id=profile.organization_id,
        project_id=profile.project_id,
        profile_name=profile.profile_name,
        description=profile.description,
        profile_version=profile.profile_version,
        status=profile.status,
        environment=profile.environment,
        owner_id=profile.owner_id,
        configuration_type=profile.configuration_type,
        target_assets=profile.target_assets,
        variables=profile.variables,
        tags=profile.tags,
        metadata=profile.metadata_,
        created_at=profile.created_at,
        updated_at=profile.updated_at,
    )


def version_to_response(version: ConfigurationVersion) -> ConfigurationVersionResponse:
    return ConfigurationVersionResponse(
        id=version.id,
        profile_id=version.profile_id,
        version_number=version.version_number,
        branch=version.branch,
        content=version.content,
        change_summary=version.change_summary,
        changed_by=version.changed_by,
        approved_by=version.approved_by,
        approved_at=version.approved_at,
        created_at=version.created_at,
    )


def rollback_to_response(rollback: ConfigurationRollback) -> ConfigurationRollbackResponse:
    return ConfigurationRollbackResponse(
        id=rollback.id,
        profile_id=rollback.profile_id,
        from_version_id=rollback.from_version_id,
        to_version_id=rollback.to_version_id,
        rollback_type=rollback.rollback_type,
        status=rollback.status,
        requested_by=rollback.requested_by,
        approved_by=rollback.approved_by,
        completed_at=rollback.completed_at,
        reason=rollback.reason,
    )


def backup_to_response(backup: ConfigurationBackup) -> ConfigurationBackupResponse:
    return ConfigurationBackupResponse(
        id=backup.id,
        profile_id=backup.profile_id,
        backup_type=backup.backup_type,
        status=backup.status,
        checksum=backup.checksum,
        encrypted=backup.encrypted,
        retention_until=backup.retention_until,
        created_at=backup.created_at,
    )


def restore_job_to_response(job: ConfigurationRestoreJob) -> ConfigurationRestoreJobResponse:
    return ConfigurationRestoreJobResponse(
        id=job.id,
        backup_id=job.backup_id,
        profile_id=job.profile_id,
        restore_type=job.restore_type,
        status=job.status,
        preview_only=job.preview_only,
        requested_by=job.requested_by,
        completed_at=job.completed_at,
    )


@router.get("", response_model=SuccessResponse[list[ConfigurationProfileResponse]])
async def list_profiles(
    organization_id: UUID, profiles: ProfileSvc, _caller: CurrentUserId
) -> SuccessResponse[list[ConfigurationProfileResponse]]:
    """List every configuration profile in *organization_id*."""
    records = await profiles.list_for_org(organization_id)
    data = [profile_to_response(record) for record in records]
    return SuccessResponse(message="Configuration profiles retrieved.", data=data, meta=_meta())


@router.get("/{profile_id}", response_model=SuccessResponse[ConfigurationProfileResponse])
async def get_profile(
    profile_id: UUID, profiles: ProfileSvc, _caller: CurrentUserId
) -> SuccessResponse[ConfigurationProfileResponse]:
    """Return one configuration profile.

    Raises:
        NotFoundError: If no such profile exists.
    """
    profile = await profiles.get_by_id(profile_id)
    return SuccessResponse(
        message="Configuration profile retrieved.", data=profile_to_response(profile), meta=_meta()
    )


@router.post("", response_model=SuccessResponse[ConfigurationProfileResponse], status_code=201)
async def create_profile(
    body: ConfigurationProfileCreateRequest, profiles: ProfileSvc, caller: CurrentUserId
) -> SuccessResponse[ConfigurationProfileResponse]:
    """Define a new configuration profile ("Create")."""
    profile = await profiles.create(
        organization_id=body.organization_id,
        project_id=body.project_id,
        profile_name=body.profile_name,
        description=body.description,
        environment=body.environment,
        owner_id=body.owner_id,
        configuration_type=body.configuration_type,
        target_assets=body.target_assets,
        variables=body.variables,
        tags=body.tags,
        metadata=body.metadata,
        created_by=caller,
    )
    return SuccessResponse(
        message="Configuration profile created.", data=profile_to_response(profile), meta=_meta()
    )


@router.put("/{profile_id}", response_model=SuccessResponse[ConfigurationProfileResponse])
async def update_profile(
    profile_id: UUID,
    body: ConfigurationProfileUpdateRequest,
    profiles: ProfileSvc,
    caller: CurrentUserId,
) -> SuccessResponse[ConfigurationProfileResponse]:
    """Replace a configuration profile's mutable fields ("Update")."""
    profile = await profiles.update(
        profile_id,
        actor_id=caller,
        profile_name=body.profile_name,
        description=body.description,
        status=body.status,
        environment=body.environment,
        owner_id=body.owner_id,
        configuration_type=body.configuration_type,
        target_assets=body.target_assets,
        variables=body.variables,
        tags=body.tags,
        metadata=body.metadata,
    )
    return SuccessResponse(
        message="Configuration profile updated.", data=profile_to_response(profile), meta=_meta()
    )


@router.patch("/{profile_id}", response_model=SuccessResponse[ConfigurationProfileResponse])
async def patch_profile(
    profile_id: UUID,
    body: ConfigurationProfilePatchRequest,
    profiles: ProfileSvc,
    caller: CurrentUserId,
) -> SuccessResponse[ConfigurationProfileResponse]:
    """Update only the given fields of a configuration profile ("PATCH partial update")."""
    patch = body.model_dump(exclude_unset=True)
    profile = await profiles.patch(profile_id, actor_id=caller, **patch)
    return SuccessResponse(
        message="Configuration profile updated.", data=profile_to_response(profile), meta=_meta()
    )


@router.delete("/{profile_id}", response_model=SuccessResponse[dict[str, bool]])
async def delete_profile(
    profile_id: UUID, profiles: ProfileSvc, caller: CurrentUserId
) -> SuccessResponse[dict[str, bool]]:
    """Soft-delete a configuration profile ("Delete")."""
    await profiles.delete(profile_id, actor_id=caller)
    return SuccessResponse(
        message="Configuration profile deleted.", data={"success": True}, meta=_meta()
    )


@router.get(
    "/{profile_id}/versions", response_model=SuccessResponse[list[ConfigurationVersionResponse]]
)
async def list_profile_versions(
    profile_id: UUID, versions: VersionSvc, _caller: CurrentUserId
) -> SuccessResponse[list[ConfigurationVersionResponse]]:
    """List every version recorded for a configuration profile ("Configuration History")."""
    records = await versions.list_for_profile(profile_id)
    data = [version_to_response(record) for record in records]
    return SuccessResponse(message="Configuration versions retrieved.", data=data, meta=_meta())


@router.post(
    "/{profile_id}/rollback",
    response_model=SuccessResponse[ConfigurationRollbackResponse],
    status_code=201,
)
async def rollback_profile(
    profile_id: UUID,
    body: ConfigurationRollbackCreateRequest,
    rollbacks: RollbackSvc,
    caller: CurrentUserId,
) -> SuccessResponse[ConfigurationRollbackResponse]:
    """Request a rollback of a configuration profile to a prior version ("Rollback")."""
    rollback = await rollbacks.initiate(
        profile_id,
        to_version_id=body.to_version_id,
        rollback_type=body.rollback_type,
        requested_by=body.requested_by or caller,
        reason=body.reason,
    )
    return SuccessResponse(
        message="Rollback initiated.", data=rollback_to_response(rollback), meta=_meta()
    )


@router.post(
    "/{profile_id}/backup",
    response_model=SuccessResponse[ConfigurationBackupResponse],
    status_code=201,
)
async def backup_profile(
    profile_id: UUID, body: ConfigurationBackupCreateRequest, backups: BackupSvc
) -> SuccessResponse[ConfigurationBackupResponse]:
    """Snapshot a configuration profile's current full state ("Configuration Backup")."""
    backup = await backups.create_backup(
        profile_id,
        backup_type=body.backup_type,
        encrypted=body.encrypted,
        retention_until=body.retention_until,
    )
    return SuccessResponse(
        message="Configuration backup created.", data=backup_to_response(backup), meta=_meta()
    )


@router.post(
    "/{profile_id}/restore",
    response_model=SuccessResponse[ConfigurationRestoreJobResponse],
    status_code=201,
)
async def restore_profile(
    profile_id: UUID,
    body: ConfigurationRestoreCreateRequest,
    restores: RestoreSvc,
    caller: CurrentUserId,
) -> SuccessResponse[ConfigurationRestoreJobResponse]:
    """Restore a configuration profile from a backup ("Restore Profile")."""
    job = await restores.restore(
        profile_id,
        backup_id=body.backup_id,
        restore_type=body.restore_type,
        preview_only=body.preview_only,
        requested_by=body.requested_by or caller,
    )
    return SuccessResponse(
        message="Configuration restore completed.", data=restore_job_to_response(job), meta=_meta()
    )


__all__ = [
    "backup_to_response",
    "profile_to_response",
    "restore_job_to_response",
    "rollback_to_response",
    "router",
    "version_to_response",
]
