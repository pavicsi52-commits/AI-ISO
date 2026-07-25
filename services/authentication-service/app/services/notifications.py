"""Authentication notifications.

Per docs/030 "NOTIFICATIONS": Welcome Email, Verification Email,
Password Reset, MFA Enabled, Login Alert, Suspicious Login, Account
Locked, Password Changed. "Integrate with Prompt 025." Thin wrapper
over :class:`shared_core.notifications.manager.NotificationManager`,
always sending as :data:`~shared_core.enums.notification_type
.NotificationType.SECURITY` over
:data:`~shared_core.enums.notification_channel.NotificationChannel.EMAIL`
-- every message body here is small and fixed, so a full
:class:`shared_core.notifications.templates.TemplateRegistry`
indirection layer would add a layer of abstraction this service has no
present need for.

Every send is best-effort: a notification failure (no channel
configured, SMTP unreachable, ...) is logged and swallowed rather than
propagated, since a caller like registration or password reset must
still succeed even when email delivery itself is unavailable -- the
same "the side effect doesn't get to veto the transaction" reasoning
:class:`shared_core.notifications.manager.NotificationManager` itself
applies to routing/preferences failures.
"""

from __future__ import annotations

from shared_core.enums.notification_channel import NotificationChannel
from shared_core.enums.notification_type import NotificationType
from shared_core.exceptions.notification import NotificationError
from shared_core.logging.logger import get_logger
from shared_core.notifications.manager import NotificationManager

logger = get_logger("app.services.notifications")


class AuthNotificationService:
    """Sends every authentication-related email this service triggers, best-effort."""

    def __init__(self, manager: NotificationManager) -> None:
        self._manager = manager

    async def _send(self, *, user_id: str, body: str, subject: str) -> None:
        try:
            await self._manager.send(
                user_id=user_id,
                notification_type=NotificationType.SECURITY,
                body=body,
                channel=NotificationChannel.EMAIL,
                subject=subject,
            )
        except NotificationError:
            logger.warning(
                "Failed to send authentication notification.",
                extra={"extra_fields": {"user_id": user_id, "subject": subject}},
            )

    async def send_welcome(self, user_id: str) -> None:
        """Send the "Welcome Email" a new registration triggers."""
        await self._send(
            user_id=user_id,
            body="Welcome to AI-IOS! Your account has been created successfully.",
            subject="Welcome to AI-IOS",
        )

    async def send_verification_email(self, user_id: str, *, verification_url: str) -> None:
        """Send the "Verification Email" prompting the user to confirm their address."""
        await self._send(
            user_id=user_id,
            body=f"Please verify your email address: {verification_url}",
            subject="Verify your AI-IOS email address",
        )

    async def send_password_reset(self, user_id: str, *, reset_url: str) -> None:
        """Send the "Password Reset" email carrying the reset link."""
        await self._send(
            user_id=user_id,
            body=f"Reset your password: {reset_url}. This link expires in one hour.",
            subject="Reset your AI-IOS password",
        )

    async def send_mfa_enabled(self, user_id: str) -> None:
        """Send the "MFA Enabled" confirmation."""
        await self._send(
            user_id=user_id,
            body="Multi-factor authentication has been enabled on your account.",
            subject="MFA enabled on your AI-IOS account",
        )

    async def send_login_alert(self, user_id: str, *, ip_address: str | None) -> None:
        """Send a "Login Alert" for a new sign-in."""
        location = f" from {ip_address}" if ip_address else ""
        await self._send(
            user_id=user_id,
            body=f"A new sign-in to your account was detected{location}.",
            subject="New sign-in to your AI-IOS account",
        )

    async def send_suspicious_login(self, user_id: str, *, ip_address: str | None) -> None:
        """Send a "Suspicious Login" warning for a blocked sign-in attempt."""
        location = f" from {ip_address}" if ip_address else ""
        await self._send(
            user_id=user_id,
            body=f"A suspicious sign-in attempt{location} was blocked. If this wasn't you, "
            "please reset your password.",
            subject="Suspicious sign-in attempt blocked",
        )

    async def send_account_locked(self, user_id: str) -> None:
        """Send the "Account Locked" notice."""
        await self._send(
            user_id=user_id,
            body="Your account has been temporarily locked due to repeated failed sign-in "
            "attempts.",
            subject="Your AI-IOS account has been locked",
        )

    async def send_password_changed(self, user_id: str) -> None:
        """Send the "Password Changed" confirmation."""
        await self._send(
            user_id=user_id,
            body="Your password was just changed. If this wasn't you, contact support "
            "immediately.",
            subject="Your AI-IOS password was changed",
        )


__all__ = ["AuthNotificationService"]
