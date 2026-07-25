"""FastAPI dependency injection for the project service.

One factory function per business service, each building its own
repositories from the request-scoped database session -- routes depend
on services only, never repositories directly, keeping the DB session
management entirely inside this module. Matches
``services/organization-service/app/api/deps.py``'s established shape.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Annotated
from uuid import UUID

from fastapi import Depends, Path, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from minio import Minio
from shared_core.cache.manager import CacheManager
from shared_core.database.session import session_scope
from shared_core.exceptions.authentication import AuthenticationError
from shared_core.exceptions.authorization import AuthorizationError
from shared_core.exceptions.not_found import NotFoundError
from shared_core.notifications.manager import NotificationManager
from shared_core.queue.producer import Producer
from shared_core.security.jwt import decode_token
from shared_core.storage import StorageWrapper
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.project_role import ADMINISTRATOR_RANK, MEMBER_RANK
from app.notifications.project_notifications import ProjectNotificationService
from app.projects.membership import rank_at_least
from app.repositories.project import ProjectRepository
from app.repositories.project_activity import ProjectActivityRepository
from app.repositories.project_archive import ProjectArchiveRepository
from app.repositories.project_audit import ProjectAuditRepository
from app.repositories.project_export_job import ProjectExportJobRepository
from app.repositories.project_favorite import ProjectFavoriteRepository
from app.repositories.project_import_job import ProjectImportJobRepository
from app.repositories.project_integration import ProjectIntegrationRepository
from app.repositories.project_label import ProjectLabelRepository
from app.repositories.project_member import ProjectMemberRepository
from app.repositories.project_metadata import ProjectMetadataRepository
from app.repositories.project_note import ProjectNoteRepository
from app.repositories.project_preferences import ProjectPreferencesRepository
from app.repositories.project_resource import ProjectResourceRepository
from app.repositories.project_role import ProjectRoleRepository
from app.repositories.project_settings import ProjectSettingsRepository
from app.repositories.project_statistics import ProjectStatisticsRepository
from app.repositories.project_tag import ProjectTagRepository
from app.repositories.project_template import ProjectTemplateRepository
from app.services.activity import ProjectActivityService
from app.services.archive import ProjectArchiveService
from app.services.audit import ProjectAuditService
from app.services.export_service import ProjectExportService
from app.services.favorite import ProjectFavoriteService
from app.services.import_service import ProjectImportService
from app.services.integration import ProjectIntegrationService
from app.services.label import ProjectLabelService
from app.services.member import ProjectMemberService
from app.services.metadata import ProjectMetadataService
from app.services.note import ProjectNoteService
from app.services.preferences import ProjectPreferencesService
from app.services.project import ProjectService
from app.services.resource import ProjectResourceService
from app.services.role import ProjectRoleService
from app.services.settings import ProjectSettingsService
from app.services.statistics import ProjectStatisticsService
from app.services.tag import ProjectTagService
from app.services.template import ProjectTemplateService

_bearer_scheme = HTTPBearer(auto_error=False)


async def get_db_session(request: Request) -> AsyncIterator[AsyncSession]:
    """Yield a request-scoped database session, committing on success.

    Per docs/018 "Transaction Session" -- see the identical rationale in
    every prior AI-IOS service's own ``get_db_session``.
    """
    session_factory = request.app.state.db_session_factory
    async with session_scope(session_factory) as session:
        yield session


DbSession = Annotated[AsyncSession, Depends(get_db_session)]


def get_cache_manager(request: Request) -> CacheManager:
    """The process-wide :class:`CacheManager`."""
    return request.app.state.cache_manager  # type: ignore[no-any-return]


def get_notification_manager(request: Request) -> NotificationManager:
    """The process-wide :class:`NotificationManager`."""
    return request.app.state.notification_manager  # type: ignore[no-any-return]


def get_minio_client(request: Request) -> Minio:
    """The process-wide MinIO client."""
    return request.app.state.minio_client  # type: ignore[no-any-return]


def get_storage_wrapper(client: Annotated[Minio, Depends(get_minio_client)]) -> StorageWrapper:
    """The current request's :class:`StorageWrapper`."""
    return StorageWrapper(client)


def get_queue_producer(request: Request) -> Producer:
    """The process-wide queue :class:`Producer`, for enqueueing import/export jobs."""
    return request.app.state.queue_producer  # type: ignore[no-any-return]


async def get_current_user_id(
    request: Request,
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer_scheme)],
) -> UUID:
    """Resolve the calling user's id from a Bearer token issued by
    ``services/authentication-service``.

    Raises:
        AuthenticationError: If no valid Bearer token is presented.
    """
    if credentials is None:
        raise AuthenticationError("Authentication required.")
    public_key = request.app.state.jwt_public_key
    claims = decode_token(credentials.credentials, public_key=public_key)
    return UUID(str(claims["sub"]))


CurrentUserId = Annotated[UUID, Depends(get_current_user_id)]


def get_notification_service(
    manager: Annotated[NotificationManager, Depends(get_notification_manager)],
) -> ProjectNotificationService:
    """The current request's :class:`ProjectNotificationService`."""
    return ProjectNotificationService(manager)


def get_activity_service(session: DbSession) -> ProjectActivityService:
    """The current request's :class:`ProjectActivityService`."""
    return ProjectActivityService(ProjectActivityRepository(session))


ActivitySvc = Annotated[ProjectActivityService, Depends(get_activity_service)]


def get_audit_service(session: DbSession) -> ProjectAuditService:
    """The current request's :class:`ProjectAuditService`."""
    return ProjectAuditService(ProjectAuditRepository(session))


AuditSvc = Annotated[ProjectAuditService, Depends(get_audit_service)]


def get_archive_service(session: DbSession) -> ProjectArchiveService:
    """The current request's :class:`ProjectArchiveService`."""
    return ProjectArchiveService(ProjectArchiveRepository(session))


ArchiveSvc = Annotated[ProjectArchiveService, Depends(get_archive_service)]


def get_role_service(session: DbSession) -> ProjectRoleService:
    """The current request's :class:`ProjectRoleService`."""
    return ProjectRoleService(ProjectRoleRepository(session))


RoleSvc = Annotated[ProjectRoleService, Depends(get_role_service)]


def get_member_service(session: DbSession, activity: ActivitySvc) -> ProjectMemberService:
    """The current request's :class:`ProjectMemberService`."""
    return ProjectMemberService(ProjectMemberRepository(session), activity)


MemberSvc = Annotated[ProjectMemberService, Depends(get_member_service)]


async def require_role_in_project(
    project_id: UUID,
    caller_id: UUID,
    members: ProjectMemberService,
    roles: ProjectRoleService,
    minimum_rank: int,
) -> None:
    """Require *caller_id* hold at least *minimum_rank* in *project_id*
    ("Validate ... project membership", "Role permissions", "Prevent
    cross-project access").

    Raises:
        AuthorizationError: If the caller is not a member, or their
            role's rank is below *minimum_rank*.
    """
    try:
        member = await members.get(project_id, caller_id)
    except NotFoundError as exc:
        raise AuthorizationError("You are not a member of this project.") from exc
    role = await roles.get_by_id(member.role_id)
    if not rank_at_least(role.rank, minimum_rank):
        raise AuthorizationError(f"This action requires a role of rank {minimum_rank} or higher.")


async def require_project_admin(
    project_id: Annotated[UUID, Path()],
    caller_id: CurrentUserId,
    members: MemberSvc,
    roles: RoleSvc,
) -> None:
    """A dependency requiring the caller hold at least the Administrator
    rank in the project named by the ``project_id`` path parameter.
    """
    await require_role_in_project(project_id, caller_id, members, roles, ADMINISTRATOR_RANK)


async def require_project_member(
    project_id: Annotated[UUID, Path()],
    caller_id: CurrentUserId,
    members: MemberSvc,
    roles: RoleSvc,
) -> None:
    """A dependency requiring the caller hold at least member rank in the
    project named by the ``project_id`` path parameter -- gates read
    access to project-scoped sub-resources, per docs/034's own "Strict
    tenant isolation"/"Prevent cross-project access" equivalent wording
    for organizations (docs/033), the same real gap
    ``services/organization-service``'s own live smoke testing caught
    and fixed.
    """
    await require_role_in_project(project_id, caller_id, members, roles, MEMBER_RANK)


def get_project_service(
    request: Request, session: DbSession, activity: ActivitySvc, archives: ArchiveSvc
) -> ProjectService:
    """The current request's fully-wired :class:`ProjectService`."""
    return ProjectService(
        ProjectRepository(session),
        ProjectSettingsRepository(session),
        ProjectPreferencesRepository(session),
        activity,
        archives,
        publish_event=getattr(request.app.state, "publish_event", None),
    )


ProjSvc = Annotated[ProjectService, Depends(get_project_service)]


def get_settings_service(session: DbSession, activity: ActivitySvc) -> ProjectSettingsService:
    """The current request's :class:`ProjectSettingsService`."""
    return ProjectSettingsService(ProjectSettingsRepository(session), activity)


SettingsSvc = Annotated[ProjectSettingsService, Depends(get_settings_service)]


def get_preferences_service(session: DbSession) -> ProjectPreferencesService:
    """The current request's :class:`ProjectPreferencesService`."""
    return ProjectPreferencesService(ProjectPreferencesRepository(session))


PreferencesSvc = Annotated[ProjectPreferencesService, Depends(get_preferences_service)]


def get_metadata_service(session: DbSession) -> ProjectMetadataService:
    """The current request's :class:`ProjectMetadataService`."""
    return ProjectMetadataService(ProjectMetadataRepository(session))


MetadataSvc = Annotated[ProjectMetadataService, Depends(get_metadata_service)]


def get_tag_service(session: DbSession) -> ProjectTagService:
    """The current request's :class:`ProjectTagService`."""
    return ProjectTagService(ProjectTagRepository(session))


TagSvc = Annotated[ProjectTagService, Depends(get_tag_service)]


def get_label_service(session: DbSession) -> ProjectLabelService:
    """The current request's :class:`ProjectLabelService`."""
    return ProjectLabelService(ProjectLabelRepository(session))


LabelSvc = Annotated[ProjectLabelService, Depends(get_label_service)]


def get_favorite_service(session: DbSession) -> ProjectFavoriteService:
    """The current request's :class:`ProjectFavoriteService`."""
    return ProjectFavoriteService(ProjectFavoriteRepository(session))


FavoriteSvc = Annotated[ProjectFavoriteService, Depends(get_favorite_service)]


def get_resource_service(session: DbSession, activity: ActivitySvc) -> ProjectResourceService:
    """The current request's :class:`ProjectResourceService`."""
    return ProjectResourceService(ProjectResourceRepository(session), activity)


ResourceSvc = Annotated[ProjectResourceService, Depends(get_resource_service)]


def get_integration_service(session: DbSession) -> ProjectIntegrationService:
    """The current request's :class:`ProjectIntegrationService`."""
    return ProjectIntegrationService(ProjectIntegrationRepository(session))


IntegrationSvc = Annotated[ProjectIntegrationService, Depends(get_integration_service)]


def get_note_service(session: DbSession) -> ProjectNoteService:
    """The current request's :class:`ProjectNoteService`."""
    return ProjectNoteService(ProjectNoteRepository(session))


NoteSvc = Annotated[ProjectNoteService, Depends(get_note_service)]


def get_statistics_service(session: DbSession) -> ProjectStatisticsService:
    """The current request's :class:`ProjectStatisticsService`."""
    return ProjectStatisticsService(
        ProjectStatisticsRepository(session), ProjectMemberRepository(session)
    )


StatisticsSvc = Annotated[ProjectStatisticsService, Depends(get_statistics_service)]


def get_template_service(session: DbSession) -> ProjectTemplateService:
    """The current request's :class:`ProjectTemplateService`."""
    return ProjectTemplateService(ProjectTemplateRepository(session))


TemplateSvc = Annotated[ProjectTemplateService, Depends(get_template_service)]


def get_import_service(
    session: DbSession,
    projects: ProjSvc,
    storage: Annotated[StorageWrapper, Depends(get_storage_wrapper)],
    request: Request,
) -> ProjectImportService:
    """The current request's fully-wired :class:`ProjectImportService`."""
    settings = request.app.state.service_settings
    return ProjectImportService(
        ProjectImportJobRepository(session),
        projects,
        storage,
        session,
        bucket=settings.import_export_bucket,
    )


ImportSvc = Annotated[ProjectImportService, Depends(get_import_service)]


def get_export_service(
    session: DbSession,
    storage: Annotated[StorageWrapper, Depends(get_storage_wrapper)],
    request: Request,
) -> ProjectExportService:
    """The current request's fully-wired :class:`ProjectExportService`."""
    settings = request.app.state.service_settings
    return ProjectExportService(
        ProjectExportJobRepository(session),
        ProjectRepository(session),
        ProjectTagRepository(session),
        storage,
        session,
        bucket=settings.import_export_bucket,
    )


ExportSvc = Annotated[ProjectExportService, Depends(get_export_service)]

__all__ = [
    "ActivitySvc",
    "ArchiveSvc",
    "AuditSvc",
    "CurrentUserId",
    "DbSession",
    "ExportSvc",
    "FavoriteSvc",
    "ImportSvc",
    "IntegrationSvc",
    "LabelSvc",
    "MemberSvc",
    "MetadataSvc",
    "NoteSvc",
    "PreferencesSvc",
    "ProjSvc",
    "ResourceSvc",
    "RoleSvc",
    "SettingsSvc",
    "StatisticsSvc",
    "TagSvc",
    "TemplateSvc",
    "get_activity_service",
    "get_archive_service",
    "get_audit_service",
    "get_cache_manager",
    "get_current_user_id",
    "get_db_session",
    "get_export_service",
    "get_favorite_service",
    "get_import_service",
    "get_integration_service",
    "get_label_service",
    "get_member_service",
    "get_metadata_service",
    "get_minio_client",
    "get_note_service",
    "get_notification_manager",
    "get_notification_service",
    "get_preferences_service",
    "get_project_service",
    "get_queue_producer",
    "get_resource_service",
    "get_role_service",
    "get_settings_service",
    "get_statistics_service",
    "get_storage_wrapper",
    "get_tag_service",
    "get_template_service",
    "require_project_admin",
    "require_project_member",
    "require_role_in_project",
]
