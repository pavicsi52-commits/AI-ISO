"""FastAPI dependency injection for the secrets management service.

One factory function per business service, each building its own
repositories from the request-scoped database session -- routes depend
on services only, never repositories directly, keeping the DB session
management entirely inside this module. Matches
``services/project-service/app/api/deps.py``'s established shape.
"""

from __future__ import annotations

from collections.abc import AsyncIterator, Awaitable, Callable
from typing import Annotated
from uuid import UUID

from fastapi import Depends, Path, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from shared_core.cache.manager import CacheManager
from shared_core.database.session import session_scope
from shared_core.exceptions.authentication import AuthenticationError
from shared_core.exceptions.authorization import AuthorizationError
from shared_core.notifications.manager import NotificationManager
from shared_core.security.jwt import decode_token
from sqlalchemy.ext.asyncio import AsyncSession

from app.encryption.envelope import EnvelopeEncryption
from app.models.enums import SecretAccessAction
from app.notifications.secret_notifications import SecretNotificationService
from app.repositories.api_key import ApiKeyRepository
from app.repositories.certificate import CertificateRepository
from app.repositories.credential_set import CredentialSetRepository
from app.repositories.encryption_key import EncryptionKeyRepository
from app.repositories.key_rotation_history import KeyRotationHistoryRepository
from app.repositories.secret import SecretRepository
from app.repositories.secret_access import SecretAccessRepository
from app.repositories.secret_audit import SecretAuditRepository
from app.repositories.secret_category import SecretCategoryRepository
from app.repositories.secret_lease import SecretLeaseRepository
from app.repositories.secret_metadata import SecretMetadataRepository
from app.repositories.secret_provider import SecretProviderRepository
from app.repositories.secret_rotation import SecretRotationRepository
from app.repositories.secret_tag import SecretTagRepository
from app.repositories.secret_version import SecretVersionRepository
from app.repositories.ssh_key import SSHKeyRepository
from app.repositories.token import TokenRepository
from app.services.access import SecretAccessService
from app.services.api_key import ApiKeyService
from app.services.audit import SecretAuditService
from app.services.category import SecretCategoryService
from app.services.certificate import CertificateService
from app.services.credential_set import CredentialSetService
from app.services.encryption_key import EncryptionKeyService
from app.services.key_rotation_history import KeyRotationHistoryService
from app.services.lease import SecretLeaseService
from app.services.metadata import SecretMetadataService
from app.services.provider import SecretProviderService
from app.services.rotation_history import SecretRotationHistoryService
from app.services.secret import SecretService
from app.services.secret_version import SecretVersionService
from app.services.ssh_key import SSHKeyService
from app.services.tag import SecretTagService
from app.services.token import TokenService

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


def get_notification_service(
    manager: Annotated[NotificationManager, Depends(get_notification_manager)],
) -> SecretNotificationService:
    """The current request's :class:`SecretNotificationService`."""
    return SecretNotificationService(manager)


def get_envelope_encryption(request: Request) -> EnvelopeEncryption:
    """The process-wide :class:`EnvelopeEncryption`, built once at startup
    from the local master key file.
    """
    return request.app.state.envelope_encryption  # type: ignore[no-any-return]


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


def get_key_rotation_history_service(session: DbSession) -> KeyRotationHistoryService:
    """The current request's :class:`KeyRotationHistoryService`."""
    return KeyRotationHistoryService(KeyRotationHistoryRepository(session))


KeyRotationHistorySvc = Annotated[
    KeyRotationHistoryService, Depends(get_key_rotation_history_service)
]


def get_encryption_key_service(
    session: DbSession,
    envelope: Annotated[EnvelopeEncryption, Depends(get_envelope_encryption)],
    history: KeyRotationHistorySvc,
    request: Request,
) -> EncryptionKeyService:
    """The current request's :class:`EncryptionKeyService`."""
    return EncryptionKeyService(
        EncryptionKeyRepository(session),
        envelope,
        history,
        publish_event=getattr(request.app.state, "publish_event", None),
    )


EncryptionKeySvc = Annotated[EncryptionKeyService, Depends(get_encryption_key_service)]


def get_secret_version_service(session: DbSession, keys: EncryptionKeySvc) -> SecretVersionService:
    """The current request's :class:`SecretVersionService`."""
    return SecretVersionService(SecretVersionRepository(session), keys)


SecretVersionSvc = Annotated[SecretVersionService, Depends(get_secret_version_service)]


def get_secret_tag_service(session: DbSession) -> SecretTagService:
    """The current request's :class:`SecretTagService`."""
    return SecretTagService(SecretTagRepository(session))


SecretTagSvc = Annotated[SecretTagService, Depends(get_secret_tag_service)]


def get_rotation_history_service(session: DbSession) -> SecretRotationHistoryService:
    """The current request's :class:`SecretRotationHistoryService`."""
    return SecretRotationHistoryService(SecretRotationRepository(session))


RotationHistorySvc = Annotated[SecretRotationHistoryService, Depends(get_rotation_history_service)]


def get_audit_service(session: DbSession) -> SecretAuditService:
    """The current request's :class:`SecretAuditService`."""
    return SecretAuditService(SecretAuditRepository(session))


AuditSvc = Annotated[SecretAuditService, Depends(get_audit_service)]


def get_secret_service(
    session: DbSession,
    versions: SecretVersionSvc,
    tags: SecretTagSvc,
    rotation_history: RotationHistorySvc,
    audit: AuditSvc,
    request: Request,
) -> SecretService:
    """The current request's fully-wired :class:`SecretService`."""
    return SecretService(
        SecretRepository(session),
        versions,
        tags,
        rotation_history,
        audit,
        publish_event=getattr(request.app.state, "publish_event", None),
    )


SecretSvc = Annotated[SecretService, Depends(get_secret_service)]


def get_access_service(session: DbSession) -> SecretAccessService:
    """The current request's :class:`SecretAccessService`."""
    return SecretAccessService(SecretAccessRepository(session))


AccessSvc = Annotated[SecretAccessService, Depends(get_access_service)]


def get_lease_service(
    session: DbSession, versions: SecretVersionSvc, request: Request
) -> SecretLeaseService:
    """The current request's :class:`SecretLeaseService`."""
    return SecretLeaseService(
        SecretLeaseRepository(session),
        versions,
        publish_event=getattr(request.app.state, "publish_event", None),
    )


LeaseSvc = Annotated[SecretLeaseService, Depends(get_lease_service)]


def get_certificate_service(
    session: DbSession, secrets: SecretSvc, request: Request
) -> CertificateService:
    """The current request's :class:`CertificateService`."""
    return CertificateService(
        CertificateRepository(session),
        secrets,
        publish_event=getattr(request.app.state, "publish_event", None),
    )


CertificateSvc = Annotated[CertificateService, Depends(get_certificate_service)]


def get_ssh_key_service(session: DbSession, secrets: SecretSvc) -> SSHKeyService:
    """The current request's :class:`SSHKeyService`."""
    return SSHKeyService(SSHKeyRepository(session), secrets)


SSHKeySvc = Annotated[SSHKeyService, Depends(get_ssh_key_service)]


def get_api_key_service(session: DbSession, secrets: SecretSvc) -> ApiKeyService:
    """The current request's :class:`ApiKeyService`."""
    return ApiKeyService(ApiKeyRepository(session), secrets)


ApiKeySvc = Annotated[ApiKeyService, Depends(get_api_key_service)]


def get_provider_service(session: DbSession) -> SecretProviderService:
    """The current request's :class:`SecretProviderService`."""
    return SecretProviderService(SecretProviderRepository(session))


ProviderSvc = Annotated[SecretProviderService, Depends(get_provider_service)]


def get_metadata_service(session: DbSession) -> SecretMetadataService:
    """The current request's :class:`SecretMetadataService`."""
    return SecretMetadataService(SecretMetadataRepository(session))


def get_category_service(session: DbSession) -> SecretCategoryService:
    """The current request's :class:`SecretCategoryService`."""
    return SecretCategoryService(SecretCategoryRepository(session))


def get_credential_set_service(session: DbSession) -> CredentialSetService:
    """The current request's :class:`CredentialSetService`."""
    return CredentialSetService(CredentialSetRepository(session))


def get_token_service(session: DbSession) -> TokenService:
    """The current request's :class:`TokenService`."""
    return TokenService(TokenRepository(session))


def require_secret_action(
    action: SecretAccessAction,
) -> Callable[[UUID, UUID, SecretService, SecretAccessService], Awaitable[None]]:
    """Build a dependency requiring the caller either own the secret named
    by the ``secret_id`` path parameter, or hold a non-expired access
    grant naming *action* ("SECRET ACCESS"). Self-contained resolution of
    docs/035's own "Integrate with Prompt 032 RBAC" -- see
    ``app/services/access.py``'s module docstring.
    """

    async def _dependency(
        secret_id: Annotated[UUID, Path()],
        caller_id: CurrentUserId,
        secrets: SecretSvc,
        access: AccessSvc,
    ) -> None:
        secret = await secrets.get_by_id(secret_id)
        if secret.owner_id == caller_id:
            return
        if await access.has_action(secret_id, caller_id, action):
            return
        raise AuthorizationError(f"You do not have {action.value!r} access to this secret.")

    return _dependency


__all__ = [
    "AccessSvc",
    "ApiKeySvc",
    "AuditSvc",
    "CertificateSvc",
    "CurrentUserId",
    "DbSession",
    "EncryptionKeySvc",
    "KeyRotationHistorySvc",
    "LeaseSvc",
    "ProviderSvc",
    "RotationHistorySvc",
    "SSHKeySvc",
    "SecretSvc",
    "SecretTagSvc",
    "SecretVersionSvc",
    "get_access_service",
    "get_api_key_service",
    "get_audit_service",
    "get_cache_manager",
    "get_category_service",
    "get_certificate_service",
    "get_credential_set_service",
    "get_current_user_id",
    "get_db_session",
    "get_encryption_key_service",
    "get_envelope_encryption",
    "get_key_rotation_history_service",
    "get_lease_service",
    "get_metadata_service",
    "get_notification_manager",
    "get_notification_service",
    "get_provider_service",
    "get_rotation_history_service",
    "get_secret_service",
    "get_secret_tag_service",
    "get_secret_version_service",
    "get_ssh_key_service",
    "get_token_service",
    "require_secret_action",
]
