"""Incident notifications (docs/052 "NOTIFICATIONS").

Integrates ``shared_core``'s notification manager (Prompt 025) using the
best-effort ``_send`` pattern every prior AI-IOS service established:
**a notification failure never blocks the operation that triggered it.**

Here that matters most on the escalation path. An SLA about to breach
must still be recorded as about to breach even if the page that was
supposed to warn somebody never went out -- the alternative, refusing to
progress the incident because a notification failed, would mean an
unreachable pager service silently disables the platform's own
escalation policy at exactly the moment it is needed most.
"""

from __future__ import annotations

from shared_core.enums.notification_channel import NotificationChannel
from shared_core.enums.notification_type import NotificationType
from shared_core.exceptions.notification import NotificationError
from shared_core.logging.logger import get_logger
from shared_core.notifications.manager import NotificationManager

logger = get_logger("app.notifications.incident_notifications")


class IncidentNotificationService:
    """Sends every incident notification, best-effort."""

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
                "Failed to send an incident notification.",
                extra={"extra_fields": {"user_id": user_id, "subject": subject}},
            )

    async def send_incident_created(
        self, user_id: str, *, reference: str, title: str, priority: str
    ) -> None:
        """Notify that a new incident exists."""
        await self._send(
            user_id=user_id,
            subject=f"[{priority}] Incident opened: {reference}",
            body=f"{reference} -- {title} -- was opened at priority {priority}.",
            notification_type=NotificationType.WARNING,
        )

    async def send_assignment(
        self, user_id: str, *, reference: str, title: str, method: str
    ) -> None:
        """Notify a responder that an incident is now theirs."""
        await self._send(
            user_id=user_id,
            subject=f"Assigned: {reference}",
            body=f"{reference} -- {title} -- was assigned to you ({method}).",
            notification_type=NotificationType.INFORMATION,
        )

    async def send_escalation(
        self, user_id: str, *, reference: str, title: str, level: int, reason: str
    ) -> None:
        """Notify an escalation target that an incident has reached them.

        The page an unmet SLA actually produces. Carries the reason
        rather than just the level, because the person being escalated
        to is being asked to act on an incident they may be seeing for
        the first time.
        """
        await self._send(
            user_id=user_id,
            subject=f"Escalated (level {level}): {reference}",
            body=f"{reference} -- {title} -- escalated to you at level {level}. {reason}",
            notification_type=NotificationType.ERROR,
        )

    async def send_major_incident_declared(
        self, user_id: str, *, reference: str, title: str, commander_id: str | None
    ) -> None:
        """Notify a stakeholder that an incident has gone major."""
        commander = (
            f"Incident commander: {commander_id}." if commander_id else "No commander assigned yet."
        )
        await self._send(
            user_id=user_id,
            subject=f"Major incident declared: {reference}",
            body=f"{reference} -- {title} -- has been declared a major incident. {commander}",
            notification_type=NotificationType.ERROR,
        )

    async def send_sla_breach(
        self, user_id: str, *, reference: str, title: str, sla_kind: str
    ) -> None:
        """Notify that an SLA clock has run out.

        Sent on breach, distinct from the escalation it likely also
        triggers -- an SLA breach and an escalation firing are two facts,
        and a recipient who only gets the escalation cannot tell from it
        alone which clock was the one that ran out.
        """
        await self._send(
            user_id=user_id,
            subject=f"SLA breached ({sla_kind}): {reference}",
            body=f"{reference} -- {title} -- breached its {sla_kind} SLA.",
            notification_type=NotificationType.ERROR,
        )

    async def send_resolution(self, user_id: str, *, reference: str, title: str) -> None:
        """Notify that an incident was resolved."""
        await self._send(
            user_id=user_id,
            subject=f"Resolved: {reference}",
            body=f"{reference} -- {title} -- was marked resolved.",
            notification_type=NotificationType.SUCCESS,
        )

    async def send_postmortem_due(
        self, user_id: str, *, reference: str, title: str, resolved_days_ago: int
    ) -> None:
        """Remind an owner that a major incident's postmortem is overdue.

        The reminder a postmortem process actually depends on: a
        postmortem that never gets written is the single most common way
        a "blameless learning culture" quietly stops producing any
        learning.
        """
        await self._send(
            user_id=user_id,
            subject=f"Postmortem overdue: {reference}",
            body=(
                f"{reference} -- {title} -- was resolved {resolved_days_ago} day(s) ago "
                "and has no postmortem yet."
            ),
            notification_type=NotificationType.WARNING,
        )


__all__ = ["IncidentNotificationService"]
