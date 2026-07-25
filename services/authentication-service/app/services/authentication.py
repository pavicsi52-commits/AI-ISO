"""Registration, login, and logout orchestration.

Per docs/030 "AUTHENTICATION METHODS": Username + Password. Ties
together every other service in this package to implement the full
register/login/logout flow: password verification, MFA challenge,
account lockout, device tracking, session/token issuance, audit,
notifications, and domain events.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from uuid import UUID

from shared_core.enums.audit_action import AuditAction
from shared_core.events.base import DomainEvent
from shared_core.exceptions.authentication import AuthenticationError
from shared_core.exceptions.conflict import ConflictError
from shared_core.security.refresh import TokenPair

from app.audit.audit import AuditService
from app.constants import DEFAULT_ORGANIZATION_ID
from app.events.auth_events import (
    AccountLockedEvent,
    EmailVerifiedEvent,
    MfaDisabledEvent,
    MfaEnabledEvent,
    PasswordResetCompletedEvent,
    PasswordResetRequestedEvent,
    UserLoggedInEvent,
    UserLoggedOutEvent,
)
from app.models.credentials import UserCredential
from app.models.enums import AuthMethod, CredentialType, FailedLoginReason
from app.models.login_history import LoginHistoryEntry
from app.models.mfa import MfaDevice
from app.models.user import User
from app.repositories.credentials import UserCredentialRepository
from app.repositories.login_history import LoginHistoryRepository
from app.repositories.user import UserRepository
from app.services.devices import DeviceService
from app.services.lockout import LockoutService
from app.services.mfa import MfaService
from app.services.notifications import AuthNotificationService
from app.services.passwords import PasswordService
from app.services.sessions import SessionService
from app.services.tokens import TokenService
from app.services.verification import VerificationService

EventPublisher = Callable[[DomainEvent], Awaitable[None]]


@dataclass(frozen=True, slots=True)
class LoginResult:
    """The outcome of one login attempt: either issued tokens, or an MFA challenge.

    The client resubmits the exact same request with ``mfa_code`` filled
    in to complete a challenged login -- ``mfa_challenge_id`` is
    correlation information for the client's UX, not a security
    boundary of its own (the password is re-verified on the follow-up
    call regardless), so it needs no separate challenge-store subsystem.
    """

    tokens: TokenPair | None = None
    user: User | None = None
    mfa_challenge_id: str | None = None

    @property
    def requires_mfa(self) -> bool:
        """Whether this result is an MFA challenge rather than issued tokens."""
        return self.mfa_challenge_id is not None


class AuthenticationService:
    """Registers, authenticates, and logs out users."""

    def __init__(
        self,
        users: UserRepository,
        credentials: UserCredentialRepository,
        login_history: LoginHistoryRepository,
        passwords: PasswordService,
        tokens: TokenService,
        sessions: SessionService,
        lockout: LockoutService,
        mfa: MfaService,
        devices: DeviceService,
        verification: VerificationService,
        audit: AuditService,
        notifications: AuthNotificationService,
        *,
        publish_event: EventPublisher | None = None,
    ) -> None:
        self._users = users
        self._credentials = credentials
        self._login_history = login_history
        self._passwords = passwords
        self._tokens = tokens
        self._sessions = sessions
        self._lockout = lockout
        self._mfa = mfa
        self._devices = devices
        self._verification = verification
        self._audit = audit
        self._notifications = notifications
        self._publish_event = publish_event

    async def _publish(self, event: DomainEvent) -> None:
        if self._publish_event is not None:
            await self._publish_event(event)

    async def register(self, *, email: str, password: str, display_name: str | None) -> User:
        """Register a new user with a password credential ("Username + Password").

        Raises:
            ConflictError: If *email* is already registered.
        """
        normalized_email = email.lower()
        if await self._users.get_by_email(normalized_email) is not None:
            raise ConflictError(f"Email {email!r} is already registered.")

        user = await self._users.create(
            User(
                email=normalized_email,
                display_name=display_name,
                organization_id=DEFAULT_ORGANIZATION_ID,
            )
        )
        hashed = self._passwords.hash(password)
        await self._credentials.create(
            UserCredential(
                user_id=user.id,
                credential_type=CredentialType.PASSWORD,
                hashed_password=hashed,
                password_changed_at=datetime.now(UTC),
                organization_id=DEFAULT_ORGANIZATION_ID,
            )
        )
        await self._passwords.record(user.id, hashed)
        await self._audit.record(AuditAction.CREATE, user_id=user.id, operation="register")

        await self._notifications.send_welcome(str(user.id))
        verification_token = await self._verification.create_token(user)
        await self._notifications.send_verification_email(
            str(user.id), verification_url=f"/auth/verify-email?token={verification_token}"
        )
        return user

    async def verify_email(self, token: str) -> User:
        """Verify an email address using a token from the verification email.

        Raises:
            AuthenticationError: If *token* is invalid, expired, or already used.
        """
        record = await self._verification.consume(token)
        user = await self._users.get_by_id(record.user_id)
        assert user is not None  # the token's user_id has a foreign key to users.id
        user.is_email_verified = True
        await self._audit.record(AuditAction.UPDATE, user_id=user.id, operation="email_verified")
        await self._publish(
            EmailVerifiedEvent(
                source_service="authentication-service", payload={"user_id": str(user.id)}
            )
        )
        return user

    async def resend_verification(self, email: str) -> None:
        """Resend the email verification link.

        Never reveals whether *email* is registered or already
        verified -- always succeeds from the caller's perspective.
        """
        user = await self._users.get_by_email(email.lower())
        if user is None or user.is_email_verified:
            return
        verification_token = await self._verification.create_token(user)
        await self._notifications.send_verification_email(
            str(user.id), verification_url=f"/auth/verify-email?token={verification_token}"
        )

    async def enable_mfa(self, user: User) -> tuple[MfaDevice, str, list[str]]:
        """Enroll a new TOTP device for *user*, returning ``(device, otpauth_uri, recovery_codes)``.

        Not enforced at login until confirmed via :meth:`confirm_mfa`.
        """
        device, recovery_codes = await self._mfa.enable(user.id)
        otpauth_uri = self._mfa.build_otpauth_uri(device.secret, email=user.email)
        return device, otpauth_uri, recovery_codes

    async def confirm_mfa(self, user: User, code: str) -> None:
        """Confirm a just-enrolled TOTP device, enforcing MFA on future logins ("MFA Enabled").

        Raises:
            AuthenticationError: If no device is pending, or *code* doesn't verify.
        """
        await self._mfa.confirm_enrollment(user.id, code)
        await self._audit.record(AuditAction.UPDATE, user_id=user.id, operation="mfa_enabled")
        await self._notifications.send_mfa_enabled(str(user.id))
        await self._publish(
            MfaEnabledEvent(
                source_service="authentication-service", payload={"user_id": str(user.id)}
            )
        )

    async def disable_mfa(self, user: User, code: str) -> None:
        """Disable MFA for *user*, requiring a valid code first ("MFA Disabled").

        Raises:
            AuthenticationError: If *code* doesn't verify.
        """
        if not await self._mfa.verify(user.id, code):
            raise AuthenticationError("Invalid MFA code.")
        await self._mfa.disable(user.id)
        await self._audit.record(AuditAction.UPDATE, user_id=user.id, operation="mfa_disabled")
        await self._publish(
            MfaDisabledEvent(
                source_service="authentication-service", payload={"user_id": str(user.id)}
            )
        )

    async def login(
        self,
        *,
        email: str,
        password: str,
        mfa_code: str | None = None,
        ip_address: str | None = None,
        user_agent: str | None = None,
        device_fingerprint: str | None = None,
    ) -> LoginResult:
        """Authenticate with email and password, completing MFA if required ("Password Login").

        An inactive (soft-deleted) account is indistinguishable from an
        unknown email here -- :meth:`~app.repositories.user
        .UserRepository.get_by_email` already excludes it, so it never
        reaches a separate check, keeping account status from leaking
        to an unauthenticated caller.

        Raises:
            AuthenticationError: If credentials are invalid, the
                account is locked, or MFA verification fails.
        """
        normalized_email = email.lower()
        user = await self._users.get_by_email(normalized_email)
        if user is None:
            await self._record_failed_login(
                normalized_email,
                reason=FailedLoginReason.ACCOUNT_NOT_FOUND,
                ip_address=ip_address,
                user_agent=user_agent,
            )
            raise AuthenticationError("Invalid email or password.")

        if self._lockout.is_locked(user):
            raise AuthenticationError("Account is locked. Try again later.")

        credential = await self._credentials.get_for_user(user.id)
        password_ok = (
            credential is not None
            and credential.hashed_password is not None
            and self._passwords.verify(password, credential.hashed_password)
        )
        if not password_ok:
            await self._record_failed_login(
                normalized_email,
                reason=FailedLoginReason.INVALID_CREDENTIALS,
                user_id=user.id,
                ip_address=ip_address,
                user_agent=user_agent,
            )
            raise AuthenticationError("Invalid email or password.")

        if await self._mfa.has_verified_device(user.id):
            if mfa_code is None:
                return LoginResult(mfa_challenge_id=str(user.id))
            if not await self._mfa.verify(user.id, mfa_code):
                await self._record_failed_login(
                    normalized_email,
                    reason=FailedLoginReason.MFA_FAILED,
                    user_id=user.id,
                    ip_address=ip_address,
                    user_agent=user_agent,
                )
                raise AuthenticationError("Invalid MFA code.")

        session = await self._sessions.create(user.id, ip_address=ip_address, user_agent=user_agent)
        tokens = await self._tokens.issue(user.id, session_id=session.id)

        if device_fingerprint is not None:
            await self._devices.record_login(
                user.id, device_fingerprint=device_fingerprint, ip_address=ip_address
            )
        await self._login_history.create(
            LoginHistoryEntry(
                user_id=user.id,
                method=AuthMethod.PASSWORD,
                ip_address=ip_address,
                user_agent=user_agent,
                organization_id=DEFAULT_ORGANIZATION_ID,
            )
        )
        user.last_login_at = datetime.now(UTC)
        await self._audit.record(AuditAction.LOGIN, user_id=user.id, ip_address=ip_address)
        await self._notifications.send_login_alert(str(user.id), ip_address=ip_address)
        await self._publish(
            UserLoggedInEvent(
                source_service="authentication-service", payload={"user_id": str(user.id)}
            )
        )
        return LoginResult(tokens=tokens, user=user)

    async def _record_failed_login(
        self,
        identifier: str,
        *,
        reason: FailedLoginReason,
        user_id: UUID | None = None,
        ip_address: str | None,
        user_agent: str | None,
    ) -> None:
        await self._lockout.record_failure(
            identifier,
            reason=reason,
            user_id=user_id,
            ip_address=ip_address,
            user_agent=user_agent,
        )
        await self._audit.record(
            AuditAction.LOGIN_FAILED,
            user_id=user_id,
            ip_address=ip_address,
            outcome="failure",
            reason=reason.value,
        )
        if user_id is None:
            return
        lockout_until = await self._lockout.compute_lockout_until(identifier)
        if lockout_until is None:
            return
        user = await self._users.get_by_id(user_id)
        if user is None:
            return
        user.locked_until = lockout_until
        await self._notifications.send_account_locked(str(user.id))
        await self._publish(
            AccountLockedEvent(
                source_service="authentication-service", payload={"user_id": str(user.id)}
            )
        )

    async def forgot_password(self, email: str) -> None:
        """Request a password reset ("Password Reset Requested").

        Never reveals whether *email* is registered -- always succeeds
        from the caller's perspective, against account enumeration.
        """
        user = await self._users.get_by_email(email.lower())
        if user is None:
            return
        raw_token = await self._passwords.create_reset_token(user)
        await self._notifications.send_password_reset(
            str(user.id), reset_url=f"/auth/reset-password?token={raw_token}"
        )
        await self._audit.record(
            AuditAction.UPDATE, user_id=user.id, operation="password_reset_requested"
        )
        await self._publish(
            PasswordResetRequestedEvent(
                source_service="authentication-service", payload={"user_id": str(user.id)}
            )
        )

    async def reset_password(self, *, token: str, new_password: str) -> None:
        """Complete a password reset ("Password Reset Completed").

        Raises:
            AuthenticationError: If *token* is invalid, expired, or already used.
            ValidationError: If *new_password* matches one of the user's recent passwords.
        """
        record = await self._passwords.consume_reset_token(token)
        await self._passwords.require_not_reused(record.user_id, new_password)
        hashed = self._passwords.hash(new_password)

        credential = await self._credentials.get_for_user(record.user_id)
        if credential is not None:
            credential.hashed_password = hashed
            credential.password_changed_at = datetime.now(UTC)
        await self._passwords.record(record.user_id, hashed)
        await self._sessions.terminate_all_for_user(record.user_id, reason="password_reset")

        await self._audit.record(AuditAction.PASSWORD_CHANGED, user_id=record.user_id)
        await self._notifications.send_password_changed(str(record.user_id))
        await self._publish(
            PasswordResetCompletedEvent(
                source_service="authentication-service",
                payload={"user_id": str(record.user_id)},
            )
        )

    async def logout(self, *, refresh_token: str) -> None:
        """Log out: revoke the refresh token and terminate its session ("Logout")."""
        claims = await self._tokens.decode_refresh_token(refresh_token)
        session_db_id = await self._tokens.revoke_refresh_token(str(claims.get("jti", "")))
        if session_db_id is not None:
            session = await self._sessions.get_by_db_id(session_db_id)
            if session is not None:
                await self._sessions.terminate(session.session_id, reason="logout")
        user_id = UUID(str(claims["sub"]))
        await self._audit.record(AuditAction.LOGOUT, user_id=user_id)
        await self._publish(
            UserLoggedOutEvent(
                source_service="authentication-service", payload={"user_id": str(user_id)}
            )
        )


__all__ = ["AuthenticationService", "LoginResult"]
