"""Policy engine notifications (docs/050 "NOTIFICATIONS").

Integrates ``shared_core``'s notification manager (Prompt 025) using the
best-effort ``_send`` pattern every prior AI-IOS service established:
**a notification failure never blocks the operation that triggered it.**

That trade is sharper here than elsewhere. This service sits in front of
every protected operation on the platform, so a notification path that
could raise would turn an unreachable SMTP server into a platform-wide
authorization outage.
"""

from __future__ import annotations

from shared_core.enums.notification_channel import NotificationChannel
from shared_core.enums.notification_type import NotificationType
from shared_core.exceptions.notification import NotificationError
from shared_core.logging.logger import get_logger
from shared_core.notifications.manager import NotificationManager

logger = get_logger("app.notifications.policy_notifications")


class PolicyNotificationService:
    """Sends every policy-engine notification, best-effort."""

    def __init__(self, manager: NotificationManager) -> None:
        self._manager = manager

    async def _send(
        self, *, user_id: str, subject: str, body: str, notification_type: NotificationType
    ) -> None:
        try:
            await self._manager.send(
                user_id=user_id,
                notification_type=notification_type,
                body=body,
                channel=NotificationChannel.EMAIL,
                subject=subject,
            )
        except NotificationError:
            logger.warning(
                "Failed to send a policy notification.",
                extra={"extra_fields": {"user_id": user_id, "subject": subject}},
            )

    async def send_violation(self, user_id: str, *, title: str, severity: str, detail: str) -> None:
        """Notify that a compliance rule was broken."""
        await self._send(
            user_id=user_id,
            subject=f"Policy violation ({severity}): {title}",
            body=f"A policy violation was recorded: {detail}",
            notification_type=NotificationType.WARNING,
        )

    async def send_approval_required(
        self, user_id: str, *, resource: str, action: str, expires_at: str
    ) -> None:
        """Notify that an operation is waiting on a sign-off."""
        await self._send(
            user_id=user_id,
            subject=f"Approval required: {action} on {resource}",
            body=(
                f"An attempt to {action} {resource} requires approval before it can "
                f"proceed. The request expires at {expires_at}."
            ),
            notification_type=NotificationType.INFO,
        )

    async def send_quota_exceeded(
        self, user_id: str, *, resource: str, consumed: float, limit: float
    ) -> None:
        """Notify that a consumption budget is exhausted."""
        await self._send(
            user_id=user_id,
            subject=f"Quota exceeded: {resource}",
            body=(
                f"The quota for {resource} is exhausted: {consumed:g} of {limit:g} "
                "used. Further requests will be refused until the period resets or "
                "the limit is raised."
            ),
            notification_type=NotificationType.ERROR,
        )

    async def send_quota_warning(self, user_id: str, *, resource: str, percent: int) -> None:
        """Notify that a budget is approaching its limit.

        The notification that matters more than the exhaustion one: by
        the time a quota is spent, work is already failing.
        """
        await self._send(
            user_id=user_id,
            subject=f"Quota at {percent}%: {resource}",
            body=(
                f"The quota for {resource} is {percent}% consumed. Requests will "
                "start being refused when it reaches 100%."
            ),
            notification_type=NotificationType.WARNING,
        )

    async def send_policy_published(
        self, user_id: str, *, slug: str, version: str, effect: str
    ) -> None:
        """Notify that a policy is now live."""
        await self._send(
            user_id=user_id,
            subject=f"Policy published: {slug} v{version}",
            body=(
                f"Policy {slug!r} version {version} is now live and applying "
                f"{effect} to matching requests."
            ),
            notification_type=NotificationType.INFO,
        )

    async def send_simulation_completed(self, user_id: str, *, label: str, summary: str) -> None:
        """Notify that a simulation finished."""
        await self._send(
            user_id=user_id,
            subject=f"Policy simulation complete: {label}",
            body=summary,
            notification_type=NotificationType.INFO,
        )


__all__ = ["PolicyNotificationService"]
