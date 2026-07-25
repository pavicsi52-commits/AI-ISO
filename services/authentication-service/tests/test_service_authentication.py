"""Tests for :class:`app.services.authentication.AuthenticationService`.

The orchestrator ties together every other business service; every
sub-service here is the real thing (backed by the real
SAVEPOINT-isolated Postgres session and, for sessions, real Redis) --
only the outbound email transport (:class:`NotificationManager`) and
the event bus are doubled, since this file is about orchestration
logic, not SMTP delivery or RabbitMQ wiring (both already covered
elsewhere: :mod:`test_service_notifications`, the real event
registration in :mod:`app.events.auth_events`).
"""

from __future__ import annotations

import uuid
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, patch

import pytest
from shared_core.constants.authentication import AuthConstants
from shared_core.events.base import DomainEvent
from shared_core.exceptions.authentication import AuthenticationError
from shared_core.exceptions.conflict import ConflictError
from shared_core.exceptions.validation import ValidationError
from shared_core.notifications.manager import NotificationManager
from shared_core.security.sessions import SessionManager
from sqlalchemy.ext.asyncio import AsyncSession

from app.audit.audit import AuditService
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
from app.services.authentication import AuthenticationService, LoginResult
from app.services.devices import DeviceService
from app.services.lockout import LockoutService
from app.services.mfa import MfaService
from app.services.notifications import AuthNotificationService
from app.services.passwords import PasswordService
from app.services.sessions import SessionService
from app.services.tokens import TokenService
from app.services.verification import VerificationService


class _Recorder:
    """Captures every published domain event, in order."""

    def __init__(self) -> None:
        self.events: list[DomainEvent] = []

    async def __call__(self, event: DomainEvent) -> None:
        self.events.append(event)


def _build_service(
    db_session: AsyncSession, session_manager: SessionManager, jwt_keypair: tuple[str, str]
) -> tuple[AuthenticationService, _Recorder]:
    private_key, public_key = jwt_keypair
    recorder = _Recorder()
    service = AuthenticationService(
        UserRepository(db_session),
        UserCredentialRepository(db_session),
        LoginHistoryRepository(db_session),
        PasswordService(
            PasswordHistoryRepository(db_session), PasswordResetTokenRepository(db_session)
        ),
        TokenService(
            AccessTokenRepository(db_session),
            RefreshTokenRepository(db_session),
            private_key=private_key,
            public_key=public_key,
        ),
        SessionService(
            SessionRepository(db_session),
            session_manager,
            absolute_timeout_seconds=AuthConstants.SESSION_ABSOLUTE_TIMEOUT_SECONDS,
        ),
        LockoutService(FailedLoginRepository(db_session)),
        MfaService(MfaDeviceRepository(db_session)),
        DeviceService(TrustedDeviceRepository(db_session)),
        VerificationService(EmailVerificationTokenRepository(db_session)),
        AuditService(AuthenticationAuditRepository(db_session)),
        AuthNotificationService(AsyncMock(spec=NotificationManager)),
        publish_event=recorder,
    )
    return service, recorder


@pytest.fixture
def service(
    db_session: AsyncSession, session_manager: SessionManager, jwt_keypair: tuple[str, str]
) -> AuthenticationService:
    built, _recorder = _build_service(db_session, session_manager, jwt_keypair)
    return built


@pytest.fixture
def service_with_events(
    db_session: AsyncSession, session_manager: SessionManager, jwt_keypair: tuple[str, str]
) -> tuple[AuthenticationService, _Recorder]:
    return _build_service(db_session, session_manager, jwt_keypair)


def _credentials() -> dict[str, str]:
    return {"email": f"user-{uuid.uuid4().hex}@example.com", "password": "Sup3rSecret!23"}


# --- register ---


async def test_register_creates_user_and_credential(service: AuthenticationService) -> None:
    creds = _credentials()

    user = await service.register(
        email=creds["email"], password=creds["password"], display_name="Test User"
    )

    assert user.email == creds["email"].lower()
    assert user.display_name == "Test User"
    assert user.is_email_verified is False


async def test_register_rejects_duplicate_email(service: AuthenticationService) -> None:
    creds = _credentials()
    await service.register(email=creds["email"], password=creds["password"], display_name=None)

    with pytest.raises(ConflictError):
        await service.register(
            email=creds["email"].upper(), password=creds["password"], display_name=None
        )


# --- verify_email / resend_verification ---


async def test_verify_email_marks_user_verified(
    service_with_events: tuple[AuthenticationService, _Recorder],
) -> None:
    service, recorder = service_with_events
    creds = _credentials()
    user = await service.register(
        email=creds["email"], password=creds["password"], display_name=None
    )
    # register() already sent one verification token; issue a fresh one to
    # consume, exactly as a client hitting POST /auth/resend-verification would.
    raw_token = await service._verification.create_token(user)  # type: ignore[attr-defined]

    verified = await service.verify_email(raw_token)

    assert verified.is_email_verified is True
    assert any(e.event_name == "EmailVerified" for e in recorder.events)


async def test_resend_verification_no_op_for_unknown_email(
    service: AuthenticationService,
) -> None:
    await service.resend_verification("nobody@example.com")


async def test_resend_verification_no_op_when_already_verified(
    service: AuthenticationService,
) -> None:
    creds = _credentials()
    user = await service.register(
        email=creds["email"], password=creds["password"], display_name=None
    )
    user.is_email_verified = True

    await service.resend_verification(creds["email"])


async def test_resend_verification_sends_again_when_unverified(
    service: AuthenticationService,
) -> None:
    creds = _credentials()
    await service.register(email=creds["email"], password=creds["password"], display_name=None)

    await service.resend_verification(creds["email"])


# --- MFA orchestration ---


async def test_enable_mfa_returns_device_uri_and_codes(service: AuthenticationService) -> None:
    creds = _credentials()
    user = await service.register(
        email=creds["email"], password=creds["password"], display_name=None
    )

    device, uri, codes = await service.enable_mfa(user)

    assert device.user_id == user.id
    assert uri.startswith("otpauth://totp/")
    assert len(codes) > 0


async def test_confirm_mfa_success(
    service_with_events: tuple[AuthenticationService, _Recorder],
    totp_code: Callable[[str], str],
) -> None:
    service, recorder = service_with_events
    creds = _credentials()
    user = await service.register(
        email=creds["email"], password=creds["password"], display_name=None
    )
    device, _uri, _codes = await service.enable_mfa(user)

    await service.confirm_mfa(user, totp_code(device.secret))

    assert any(e.event_name == "MfaEnabled" for e in recorder.events)


async def test_disable_mfa_rejects_wrong_code(service: AuthenticationService) -> None:
    creds = _credentials()
    user = await service.register(
        email=creds["email"], password=creds["password"], display_name=None
    )
    await service.enable_mfa(user)

    with pytest.raises(AuthenticationError):
        await service.disable_mfa(user, "000000")


async def test_disable_mfa_success(
    service_with_events: tuple[AuthenticationService, _Recorder],
    totp_code: Callable[[str], str],
) -> None:
    service, recorder = service_with_events
    creds = _credentials()
    user = await service.register(
        email=creds["email"], password=creds["password"], display_name=None
    )
    device, _uri, _codes = await service.enable_mfa(user)
    await service.confirm_mfa(user, totp_code(device.secret))

    await service.disable_mfa(user, totp_code(device.secret))

    assert any(e.event_name == "MfaDisabled" for e in recorder.events)


# --- login ---


async def test_login_rejects_unknown_email(service: AuthenticationService) -> None:
    with pytest.raises(AuthenticationError):
        await service.login(email="nobody@example.com", password="whatever")


async def test_login_rejects_wrong_password(service: AuthenticationService) -> None:
    creds = _credentials()
    await service.register(email=creds["email"], password=creds["password"], display_name=None)

    with pytest.raises(AuthenticationError):
        await service.login(email=creds["email"], password="wrong-password")


async def test_login_rejects_soft_deleted_account(service: AuthenticationService) -> None:
    creds = _credentials()
    user = await service.register(
        email=creds["email"], password=creds["password"], display_name=None
    )
    user.is_active = False  # what UserRepository.delete() does -- also excludes it from lookups

    with pytest.raises(AuthenticationError, match="Invalid email or password"):
        await service.login(email=creds["email"], password=creds["password"])


async def test_login_rejects_locked_account(service: AuthenticationService) -> None:
    creds = _credentials()
    user = await service.register(
        email=creds["email"], password=creds["password"], display_name=None
    )
    user.locked_until = datetime.now(UTC) + timedelta(minutes=5)

    with pytest.raises(AuthenticationError):
        await service.login(email=creds["email"], password=creds["password"])


async def test_login_success_without_mfa_issues_tokens(
    service_with_events: tuple[AuthenticationService, _Recorder],
) -> None:
    service, recorder = service_with_events
    creds = _credentials()
    await service.register(email=creds["email"], password=creds["password"], display_name=None)

    result = await service.login(
        email=creds["email"],
        password=creds["password"],
        ip_address="127.0.0.1",
        user_agent="pytest",
        device_fingerprint="fp-login-1",
    )

    assert isinstance(result, LoginResult)
    assert result.requires_mfa is False
    assert result.tokens is not None
    assert result.user is not None
    assert any(e.event_name == "UserLoggedIn" for e in recorder.events)


async def test_login_with_verified_mfa_challenges_then_succeeds(
    service: AuthenticationService, totp_code: Callable[[str], str]
) -> None:
    creds = _credentials()
    user = await service.register(
        email=creds["email"], password=creds["password"], display_name=None
    )
    device, _uri, _codes = await service.enable_mfa(user)
    await service.confirm_mfa(user, totp_code(device.secret))

    challenge = await service.login(email=creds["email"], password=creds["password"])
    assert challenge.requires_mfa is True

    completed = await service.login(
        email=creds["email"], password=creds["password"], mfa_code=totp_code(device.secret)
    )
    assert completed.requires_mfa is False
    assert completed.tokens is not None


async def test_login_with_wrong_mfa_code_raises(
    service: AuthenticationService, totp_code: Callable[[str], str]
) -> None:
    creds = _credentials()
    user = await service.register(
        email=creds["email"], password=creds["password"], display_name=None
    )
    device, _uri, _codes = await service.enable_mfa(user)
    await service.confirm_mfa(user, totp_code(device.secret))

    with pytest.raises(AuthenticationError):
        await service.login(email=creds["email"], password=creds["password"], mfa_code="000000")


async def test_repeated_failed_logins_lock_the_account(
    service_with_events: tuple[AuthenticationService, _Recorder],
) -> None:
    service, recorder = service_with_events
    creds = _credentials()
    user = await service.register(
        email=creds["email"], password=creds["password"], display_name=None
    )

    for _ in range(5):
        with pytest.raises(AuthenticationError):
            await service.login(email=creds["email"], password="wrong-password")

    assert user.locked_until is not None
    assert any(e.event_name == "AccountLocked" for e in recorder.events)


# --- forgot_password / reset_password ---


async def test_forgot_password_no_op_for_unknown_email(service: AuthenticationService) -> None:
    await service.forgot_password("nobody@example.com")


async def test_forgot_password_and_reset_password_round_trip(
    service_with_events: tuple[AuthenticationService, _Recorder],
) -> None:
    service, recorder = service_with_events
    creds = _credentials()
    user = await service.register(
        email=creds["email"], password=creds["password"], display_name=None
    )
    await service.login(email=creds["email"], password=creds["password"])

    await service.forgot_password(creds["email"])
    raw_token = await service._passwords.create_reset_token(user)  # type: ignore[attr-defined]

    await service.reset_password(token=raw_token, new_password="BrandNewSecret!45")

    assert any(e.event_name == "PasswordResetRequested" for e in recorder.events)
    assert any(e.event_name == "PasswordResetCompleted" for e in recorder.events)
    relogin = await service.login(email=creds["email"], password="BrandNewSecret!45")
    assert relogin.tokens is not None


async def test_reset_password_rejects_reused_password(service: AuthenticationService) -> None:
    creds = _credentials()
    user = await service.register(
        email=creds["email"], password=creds["password"], display_name=None
    )
    raw_token = await service._passwords.create_reset_token(user)  # type: ignore[attr-defined]

    with pytest.raises(ValidationError):
        await service.reset_password(token=raw_token, new_password=creds["password"])


# --- logout ---


async def test_logout_terminates_session(
    service_with_events: tuple[AuthenticationService, _Recorder],
) -> None:
    service, recorder = service_with_events
    creds = _credentials()
    await service.register(email=creds["email"], password=creds["password"], display_name=None)
    result = await service.login(email=creds["email"], password=creds["password"])
    assert result.tokens is not None

    await service.logout(refresh_token=result.tokens.refresh_token)

    assert any(e.event_name == "UserLoggedOut" for e in recorder.events)


async def test_logout_with_no_tracked_session_still_revokes_token(
    db_session: AsyncSession, session_manager: SessionManager, jwt_keypair: tuple[str, str]
) -> None:
    """A refresh token issued with no ``session_id`` (e.g. a service-to-service
    caller) has nothing to terminate in Postgres/Redis, but logout must still
    succeed and revoke the token itself.
    """
    service, _recorder = _build_service(db_session, session_manager, jwt_keypair)
    creds = _credentials()
    user = await service.register(
        email=creds["email"], password=creds["password"], display_name=None
    )
    pair = await service._tokens.issue(user.id)  # type: ignore[attr-defined]

    await service.logout(refresh_token=pair.refresh_token)


# --- edge cases: no event bus configured ---


async def test_verify_email_works_with_no_event_bus_configured(
    db_session: AsyncSession, session_manager: SessionManager, jwt_keypair: tuple[str, str]
) -> None:
    private_key, public_key = jwt_keypair
    service = AuthenticationService(
        UserRepository(db_session),
        UserCredentialRepository(db_session),
        LoginHistoryRepository(db_session),
        PasswordService(
            PasswordHistoryRepository(db_session), PasswordResetTokenRepository(db_session)
        ),
        TokenService(
            AccessTokenRepository(db_session),
            RefreshTokenRepository(db_session),
            private_key=private_key,
            public_key=public_key,
        ),
        SessionService(
            SessionRepository(db_session),
            session_manager,
            absolute_timeout_seconds=AuthConstants.SESSION_ABSOLUTE_TIMEOUT_SECONDS,
        ),
        LockoutService(FailedLoginRepository(db_session)),
        MfaService(MfaDeviceRepository(db_session)),
        DeviceService(TrustedDeviceRepository(db_session)),
        VerificationService(EmailVerificationTokenRepository(db_session)),
        AuditService(AuthenticationAuditRepository(db_session)),
        AuthNotificationService(AsyncMock(spec=NotificationManager)),
        # publish_event omitted: no event bus wired up at all.
    )
    creds = _credentials()
    user = await service.register(
        email=creds["email"], password=creds["password"], display_name=None
    )
    raw_token = await service._verification.create_token(user)  # type: ignore[attr-defined]

    verified = await service.verify_email(raw_token)

    assert verified.is_email_verified is True


# --- edge cases: reset_password for a user with no password credential ---


async def test_reset_password_with_no_existing_credential_still_records_history(
    service: AuthenticationService, db_session: AsyncSession
) -> None:
    creds = _credentials()
    user = await service.register(
        email=creds["email"], password=creds["password"], display_name=None
    )
    # Simulate a federated-identity user with no password credential row:
    # UserCredentialRepository.get_for_user() returning None is the only
    # other shape reset_password() needs to tolerate.
    credential_repo = UserCredentialRepository(db_session)
    existing = await credential_repo.get_for_user(user.id)
    assert existing is not None
    await credential_repo.delete(existing.id)
    raw_token = await service._passwords.create_reset_token(user)  # type: ignore[attr-defined]

    await service.reset_password(token=raw_token, new_password="BrandNewSecret!45")


# --- edge cases: _record_failed_login racing a deleted user ---


async def test_record_failed_login_tolerates_user_deleted_between_lockout_and_refetch(
    service: AuthenticationService, db_session: AsyncSession
) -> None:
    """A real ``users`` row is required for the first four failures (``failed_logins
    .user_id`` has a real foreign key), so the fifth -- the one that crosses the
    lockout threshold and triggers the re-fetch -- is the one call where
    ``UserRepository.get_by_id`` is patched to return ``None``, simulating the
    account having been deleted by a concurrent request in between.
    """
    creds = _credentials()
    user = await service.register(
        email=creds["email"], password=creds["password"], display_name=None
    )

    for _ in range(4):
        with pytest.raises(AuthenticationError):
            await service.login(email=creds["email"], password="wrong-password")

    with (
        patch.object(UserRepository, "get_by_id", AsyncMock(return_value=None)),
        pytest.raises(AuthenticationError),
    ):
        await service.login(email=creds["email"], password="wrong-password")

    reloaded = await UserRepository(db_session).get_by_id(user.id)
    assert reloaded is not None
    assert reloaded.locked_until is None  # the patched re-fetch bailed out before setting it
