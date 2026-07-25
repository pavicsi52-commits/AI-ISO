"""FastAPI dependency injection for the user management service.

One factory function per business service, each building its own
repositories from the request-scoped database session -- routes depend
on services only, never repositories directly, keeping the DB session
management entirely inside this module. Matches
``services/authentication-service/app/api/deps.py``'s established shape.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Annotated
from uuid import UUID

from fastapi import Depends, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from minio import Minio
from shared_core.cache.manager import CacheManager
from shared_core.database.session import session_scope
from shared_core.exceptions.authentication import AuthenticationError
from shared_core.notifications.manager import NotificationManager
from shared_core.queue.producer import Producer
from shared_core.security.jwt import decode_token
from shared_core.storage import StorageWrapper
from sqlalchemy.ext.asyncio import AsyncSession

from app.config.settings import get_settings
from app.notifications.user_notifications import UserNotificationService
from app.repositories.activity import UserActivityRepository
from app.repositories.address import UserAddressRepository
from app.repositories.avatar import UserAvatarRepository
from app.repositories.contact import UserContactRepository
from app.repositories.export_job import UserExportJobRepository
from app.repositories.import_job import UserImportJobRepository
from app.repositories.invitation import UserInvitationRepository
from app.repositories.metadata import UserMetadataRepository
from app.repositories.note import UserNoteRepository
from app.repositories.preferences import UserPreferencesRepository
from app.repositories.profile import UserProfileRepository
from app.repositories.settings import UserSettingsRepository
from app.repositories.tag import UserTagRepository
from app.repositories.user import UserRepository
from app.services.activity import UserActivityService
from app.services.address import UserAddressService
from app.services.cache import UserCacheService
from app.services.contact import UserContactService
from app.services.export_service import UserExportService
from app.services.import_service import UserImportService
from app.services.invitation import InvitationService
from app.services.metadata import UserMetadataService
from app.services.note import UserNoteService
from app.services.preferences import UserPreferencesService
from app.services.profile import UserProfileService
from app.services.settings import UserSettingsService
from app.services.tag import UserTagService
from app.services.user import UserService
from app.storage.avatar_storage import AvatarService

_bearer_scheme = HTTPBearer(auto_error=False)


async def get_db_session(request: Request) -> AsyncIterator[AsyncSession]:
    """Yield a request-scoped database session, committing on success.

    Per docs/018 "Transaction Session" -- see the identical rationale
    in ``services/authentication-service/app/api/deps.py``'s own
    ``get_db_session``, whose live-smoke-tested fix this reuses
    directly (:func:`~shared_core.database.session.session_scope`).
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

    This service verifies identity tokens; it never issues them (see
    ``app/config/keys.py``'s docstring).

    Raises:
        AuthenticationError: If no valid Bearer token is presented.
    """
    if credentials is None:
        raise AuthenticationError("Authentication required.")
    public_key = request.app.state.jwt_public_key
    claims = decode_token(credentials.credentials, public_key=public_key)
    return UUID(str(claims["sub"]))


CurrentUserId = Annotated[UUID, Depends(get_current_user_id)]


def get_activity_service(session: DbSession) -> UserActivityService:
    """The current request's :class:`UserActivityService`."""
    return UserActivityService(UserActivityRepository(session))


ActivitySvc = Annotated[UserActivityService, Depends(get_activity_service)]


def get_notification_service(
    manager: Annotated[NotificationManager, Depends(get_notification_manager)],
) -> UserNotificationService:
    """The current request's :class:`UserNotificationService`."""
    return UserNotificationService(manager)


def get_cache_service(
    cache: Annotated[CacheManager, Depends(get_cache_manager)],
) -> UserCacheService:
    """The current request's :class:`UserCacheService`."""
    return UserCacheService(cache)


CacheSvc = Annotated[UserCacheService, Depends(get_cache_service)]


def get_user_service(
    request: Request,
    session: DbSession,
    activity: ActivitySvc,
    notifications: Annotated[UserNotificationService, Depends(get_notification_service)],
) -> UserService:
    """The current request's fully-wired :class:`UserService`."""
    return UserService(
        UserRepository(session),
        activity,
        notifications,
        publish_event=getattr(request.app.state, "publish_event", None),
    )


UserSvc = Annotated[UserService, Depends(get_user_service)]


def get_profile_service(session: DbSession, activity: ActivitySvc) -> UserProfileService:
    """The current request's :class:`UserProfileService`."""
    return UserProfileService(UserProfileRepository(session), activity)


ProfileSvc = Annotated[UserProfileService, Depends(get_profile_service)]


def get_preferences_service(session: DbSession, activity: ActivitySvc) -> UserPreferencesService:
    """The current request's :class:`UserPreferencesService`."""
    return UserPreferencesService(UserPreferencesRepository(session), activity)


PreferencesSvc = Annotated[UserPreferencesService, Depends(get_preferences_service)]


def get_settings_service(session: DbSession) -> UserSettingsService:
    """The current request's :class:`UserSettingsService`."""
    return UserSettingsService(UserSettingsRepository(session))


SettingsSvc = Annotated[UserSettingsService, Depends(get_settings_service)]


def get_address_service(session: DbSession) -> UserAddressService:
    """The current request's :class:`UserAddressService`."""
    return UserAddressService(UserAddressRepository(session))


AddressSvc = Annotated[UserAddressService, Depends(get_address_service)]


def get_contact_service(session: DbSession) -> UserContactService:
    """The current request's :class:`UserContactService`."""
    return UserContactService(UserContactRepository(session))


ContactSvc = Annotated[UserContactService, Depends(get_contact_service)]


def get_metadata_service(session: DbSession) -> UserMetadataService:
    """The current request's :class:`UserMetadataService`."""
    return UserMetadataService(UserMetadataRepository(session))


MetadataSvc = Annotated[UserMetadataService, Depends(get_metadata_service)]


def get_tag_service(session: DbSession) -> UserTagService:
    """The current request's :class:`UserTagService`."""
    return UserTagService(UserTagRepository(session))


TagSvc = Annotated[UserTagService, Depends(get_tag_service)]


def get_note_service(session: DbSession) -> UserNoteService:
    """The current request's :class:`UserNoteService`."""
    return UserNoteService(UserNoteRepository(session))


NoteSvc = Annotated[UserNoteService, Depends(get_note_service)]


def get_avatar_service(
    session: DbSession, storage: Annotated[StorageWrapper, Depends(get_storage_wrapper)]
) -> AvatarService:
    """The current request's :class:`AvatarService`."""
    settings = get_settings()
    return AvatarService(
        UserAvatarRepository(session), storage, bucket=settings.service.avatar_bucket
    )


AvatarSvc = Annotated[AvatarService, Depends(get_avatar_service)]


def get_invitation_service(
    request: Request,
    session: DbSession,
    users: UserSvc,
    activity: ActivitySvc,
    notifications: Annotated[UserNotificationService, Depends(get_notification_service)],
) -> InvitationService:
    """The current request's fully-wired :class:`InvitationService`."""
    return InvitationService(
        UserInvitationRepository(session),
        users,
        activity,
        notifications,
        publish_event=getattr(request.app.state, "publish_event", None),
    )


InvitationSvc = Annotated[InvitationService, Depends(get_invitation_service)]


def get_import_service(
    request: Request,
    session: DbSession,
    users: UserSvc,
    activity: ActivitySvc,
    storage: Annotated[StorageWrapper, Depends(get_storage_wrapper)],
) -> UserImportService:
    """The current request's fully-wired :class:`UserImportService`."""
    settings = get_settings()
    return UserImportService(
        UserImportJobRepository(session),
        users,
        activity,
        storage,
        bucket=settings.service.import_export_bucket,
        publish_event=getattr(request.app.state, "publish_event", None),
    )


ImportSvc = Annotated[UserImportService, Depends(get_import_service)]


def get_export_service(
    request: Request,
    session: DbSession,
    activity: ActivitySvc,
    storage: Annotated[StorageWrapper, Depends(get_storage_wrapper)],
) -> UserExportService:
    """The current request's fully-wired :class:`UserExportService`."""
    settings = get_settings()
    return UserExportService(
        UserExportJobRepository(session),
        UserRepository(session),
        activity,
        storage,
        bucket=settings.service.import_export_bucket,
        publish_event=getattr(request.app.state, "publish_event", None),
    )


ExportSvc = Annotated[UserExportService, Depends(get_export_service)]

__all__ = [
    "ActivitySvc",
    "AddressSvc",
    "AvatarSvc",
    "CacheSvc",
    "ContactSvc",
    "CurrentUserId",
    "DbSession",
    "ExportSvc",
    "ImportSvc",
    "InvitationSvc",
    "MetadataSvc",
    "NoteSvc",
    "PreferencesSvc",
    "ProfileSvc",
    "SettingsSvc",
    "TagSvc",
    "UserSvc",
    "get_activity_service",
    "get_address_service",
    "get_avatar_service",
    "get_cache_manager",
    "get_cache_service",
    "get_contact_service",
    "get_current_user_id",
    "get_db_session",
    "get_export_service",
    "get_import_service",
    "get_invitation_service",
    "get_metadata_service",
    "get_minio_client",
    "get_note_service",
    "get_notification_manager",
    "get_notification_service",
    "get_preferences_service",
    "get_profile_service",
    "get_queue_producer",
    "get_settings_service",
    "get_storage_wrapper",
    "get_tag_service",
    "get_user_service",
]
