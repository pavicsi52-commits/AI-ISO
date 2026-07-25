"""FastAPI dependency injection for the authentication service.

One factory function per business service, each building its own
repositories from the request-scoped database session -- routes depend
on services only, never repositories directly, keeping the DB session
management entirely inside this module.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Annotated
from uuid import UUID

from fastapi import Depends, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from shared_core.constants.authentication import AuthConstants
from shared_core.database.session import session_scope
from shared_core.exceptions.authentication import AuthenticationError
from shared_core.notifications.manager import NotificationManager
from shared_core.security.sessions import SessionManager
from sqlalchemy.ext.asyncio import AsyncSession

from app.audit.audit import AuditService
from app.models.user import User
from app.repositories.apikey import ApiKeyRepository
from app.repositories.audit import AuthenticationAuditRepository
from app.repositories.credentials import UserCredentialRepository
from app.repositories.device import TrustedDeviceRepository
from app.repositories.failed_login import FailedLoginRepository
from app.repositories.login_history import LoginHistoryRepository
from app.repositories.mfa import MfaDeviceRepository
from app.repositories.password import PasswordHistoryRepository, PasswordResetTokenRepository
from app.repositories.session import SessionRepository
from app.repositories.token import AccessTokenRepository, RefreshTokenRepository
from app.repositories.user import UserRepository
from app.repositories.verification import EmailVerificationTokenRepository
from app.services.apikeys import ApiKeyService
from app.services.authentication import AuthenticationService
from app.services.devices import DeviceService
from app.services.lockout import LockoutService
from app.services.mfa import MfaService
from app.services.notifications import AuthNotificationService
from app.services.passwords import PasswordService
from app.services.sessions import SessionService
from app.services.tokens import TokenService
from app.services.verification import VerificationService

_bearer_scheme = HTTPBearer(auto_error=False)


async def get_db_session(request: Request) -> AsyncIterator[AsyncSession]:
    """Yield a request-scoped database session.

    Per docs/018 "Transaction Session": the whole request is one unit of
    work, committed on a clean response and rolled back if the route (or
    a dependency) raises -- :func:`~shared_core.database.session.session_scope`
    is the same primitive scripts/tests use for this, reused here instead
    of a hand-rolled commit/rollback so the guarantee stays in one place.
    """
    session_factory = request.app.state.db_session_factory
    async with session_scope(session_factory) as session:
        yield session


DbSession = Annotated[AsyncSession, Depends(get_db_session)]


def get_audit_service(session: DbSession) -> AuditService:
    """The current request's :class:`AuditService`."""
    return AuditService(AuthenticationAuditRepository(session))


AuditSvc = Annotated[AuditService, Depends(get_audit_service)]


def get_token_service(request: Request, session: DbSession) -> TokenService:
    """The current request's :class:`TokenService`, using the process's shared keypair."""
    private_key, public_key = request.app.state.jwt_keypair
    return TokenService(
        AccessTokenRepository(session),
        RefreshTokenRepository(session),
        private_key=private_key,
        public_key=public_key,
    )


TokenSvc = Annotated[TokenService, Depends(get_token_service)]


def get_session_manager(request: Request) -> SessionManager:
    """The process-wide (Redis-backed) :class:`SessionManager`."""
    return request.app.state.session_manager  # type: ignore[no-any-return]


def get_session_service(
    session: DbSession, manager: Annotated[SessionManager, Depends(get_session_manager)]
) -> SessionService:
    """The current request's :class:`SessionService`."""
    return SessionService(
        SessionRepository(session),
        manager,
        absolute_timeout_seconds=AuthConstants.SESSION_ABSOLUTE_TIMEOUT_SECONDS,
    )


SessionSvc = Annotated[SessionService, Depends(get_session_service)]


def get_password_service(session: DbSession) -> PasswordService:
    """The current request's :class:`PasswordService`."""
    return PasswordService(
        PasswordHistoryRepository(session), PasswordResetTokenRepository(session)
    )


def get_lockout_service(session: DbSession) -> LockoutService:
    """The current request's :class:`LockoutService`."""
    return LockoutService(FailedLoginRepository(session))


def get_mfa_service(session: DbSession) -> MfaService:
    """The current request's :class:`MfaService`."""
    return MfaService(MfaDeviceRepository(session))


MfaSvc = Annotated[MfaService, Depends(get_mfa_service)]


def get_device_service(session: DbSession) -> DeviceService:
    """The current request's :class:`DeviceService`."""
    return DeviceService(TrustedDeviceRepository(session))


DeviceSvc = Annotated[DeviceService, Depends(get_device_service)]


def get_verification_service(session: DbSession) -> VerificationService:
    """The current request's :class:`VerificationService`."""
    return VerificationService(EmailVerificationTokenRepository(session))


def get_api_key_service(session: DbSession) -> ApiKeyService:
    """The current request's :class:`ApiKeyService`."""
    return ApiKeyService(ApiKeyRepository(session))


ApiKeySvc = Annotated[ApiKeyService, Depends(get_api_key_service)]


def get_notification_manager(request: Request) -> NotificationManager:
    """The process-wide :class:`NotificationManager`."""
    return request.app.state.notification_manager  # type: ignore[no-any-return]


def get_notification_service(
    manager: Annotated[NotificationManager, Depends(get_notification_manager)],
) -> AuthNotificationService:
    """The current request's :class:`AuthNotificationService`."""
    return AuthNotificationService(manager)


def get_authentication_service(
    request: Request,
    session: DbSession,
    passwords: Annotated[PasswordService, Depends(get_password_service)],
    tokens: TokenSvc,
    sessions: SessionSvc,
    lockout: Annotated[LockoutService, Depends(get_lockout_service)],
    mfa: MfaSvc,
    devices: DeviceSvc,
    verification: Annotated[VerificationService, Depends(get_verification_service)],
    audit: AuditSvc,
    notifications: Annotated[AuthNotificationService, Depends(get_notification_service)],
) -> AuthenticationService:
    """The current request's fully-wired :class:`AuthenticationService`."""
    return AuthenticationService(
        UserRepository(session),
        UserCredentialRepository(session),
        LoginHistoryRepository(session),
        passwords,
        tokens,
        sessions,
        lockout,
        mfa,
        devices,
        verification,
        audit,
        notifications,
        publish_event=getattr(request.app.state, "publish_event", None),
    )


AuthSvc = Annotated[AuthenticationService, Depends(get_authentication_service)]


async def get_current_user(
    session: DbSession,
    tokens: TokenSvc,
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer_scheme)],
) -> User:
    """Resolve and return the authenticated caller's :class:`User`.

    Raises:
        AuthenticationError: If no valid Bearer token is presented.
    """
    if credentials is None:
        raise AuthenticationError("Authentication required.")
    claims = await tokens.decode_access_token(credentials.credentials)
    user = await UserRepository(session).get_by_id(UUID(str(claims["sub"])))
    if user is None:
        raise AuthenticationError("Authentication required.")
    return user


CurrentUser = Annotated[User, Depends(get_current_user)]

__all__ = [
    "ApiKeySvc",
    "AuditSvc",
    "AuthSvc",
    "CurrentUser",
    "DbSession",
    "DeviceSvc",
    "MfaSvc",
    "SessionSvc",
    "TokenSvc",
    "get_api_key_service",
    "get_audit_service",
    "get_authentication_service",
    "get_current_user",
    "get_db_session",
    "get_device_service",
    "get_lockout_service",
    "get_mfa_service",
    "get_notification_manager",
    "get_notification_service",
    "get_password_service",
    "get_session_manager",
    "get_session_service",
    "get_token_service",
    "get_verification_service",
]
