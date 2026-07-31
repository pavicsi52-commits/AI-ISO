"""Compliance notifications (docs/051 "NOTIFICATIONS").

Integrates ``shared_core``'s notification manager (Prompt 025) using the
best-effort ``_send`` pattern every prior AI-IOS service established:
**a notification failure never blocks the operation that triggered it.**

Here that mostly protects long-running work. An assessment that has
walked five thousand hosts must not lose its results because an SMTP
server was unreachable at the moment it finished -- the results are the
expensive part and the email is not.
"""

from __future__ import annotations

from shared_core.enums.notification_channel import NotificationChannel
from shared_core.enums.notification_type import NotificationType
from shared_core.exceptions.notification import NotificationError
from shared_core.logging.logger import get_logger
from shared_core.notifications.manager import NotificationManager

logger = get_logger("app.notifications.compliance_notifications")


class ComplianceNotificationService:
    """Sends every compliance notification, best-effort."""

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
                "Failed to send a compliance notification.",
                extra={"extra_fields": {"user_id": user_id, "subject": subject}},
            )

    async def send_critical_failure(
        self, user_id: str, *, control_code: str, target: str, detail: str
    ) -> None:
        """Notify that a critical control is not being met."""
        await self._send(
            user_id=user_id,
            subject=f"Critical compliance failure: {control_code} on {target}",
            body=(
                f"Control {control_code} failed on {target}. {detail} "
                "This control is rated critical, so the gap is treated as urgent."
            ),
            notification_type=NotificationType.ERROR,
        )

    async def send_assessment_completed(
        self, user_id: str, *, name: str, score: float, failed: int, coverage: float
    ) -> None:
        """Notify that an assessment finished.

        Carries coverage as well as score, because a score without its
        coverage is the number people misread -- 100% across 4% of the
        estate is not compliance.
        """
        await self._send(
            user_id=user_id,
            subject=f"Compliance assessment completed: {name}",
            body=(
                f"The assessment {name!r} finished with a score of {score:.1f}% "
                f"across {coverage:.1f}% of in-scope controls, with {failed} "
                "failing control(s)."
            ),
            notification_type=NotificationType.INFORMATION,
        )

    async def send_risk_registered(
        self, user_id: str, *, reference: str, title: str, severity: str
    ) -> None:
        """Notify that a risk entered the register."""
        await self._send(
            user_id=user_id,
            subject=f"Risk registered ({severity}): {reference}",
            body=f"{reference} -- {title} -- was added to the risk register at {severity}.",
            notification_type=NotificationType.WARNING,
        )

    async def send_exception_expiring(
        self, user_id: str, *, title: str, expires_at: str, control_code: str
    ) -> None:
        """Warn that a waiver is about to lapse.

        Sent *before* expiry rather than after, because a waiver that
        lapses unannounced turns into a wave of failing controls in the
        next assessment, and the first anybody hears of it is a dashboard
        going red for a reason nobody can explain.
        """
        await self._send(
            user_id=user_id,
            subject=f"Compliance exception expiring: {title}",
            body=(
                f"The exception {title!r} covering control {control_code} expires "
                f"{expires_at}. Renew or retire it before the next assessment, or "
                "the control it waives will begin failing."
            ),
            notification_type=NotificationType.WARNING,
        )

    async def send_remediation_completed(self, user_id: str, *, title: str, verified: bool) -> None:
        """Notify that a fix was applied, and whether it was proven."""
        await self._send(
            user_id=user_id,
            subject=f"Remediation completed: {title}",
            body=(
                f"The remediation {title!r} completed and the control was re-assessed as passing."
                if verified
                else (
                    f"The remediation {title!r} completed but has not been verified. "
                    "The finding stays open until a re-assessment confirms the control "
                    "now passes."
                )
            ),
            notification_type=(NotificationType.SUCCESS if verified else NotificationType.WARNING),
        )

    async def send_evidence_missing(self, user_id: str, *, control_code: str, count: int) -> None:
        """Warn that controls could not be assessed for want of evidence.

        The notification an audit-readiness process actually needs. A
        control with no evidence is not a failure and not a pass, and
        without this it is simply absent from every report -- which is
        the shape of gap that gets discovered in the room.
        """
        await self._send(
            user_id=user_id,
            subject=f"Audit evidence missing for {control_code}",
            body=(
                f"{count} target(s) had no evidence for control {control_code}, so it "
                "could not be assessed. These controls are neither passing nor "
                "failing -- they are unmeasured, and an audit will treat them as gaps."
            ),
            notification_type=NotificationType.WARNING,
        )


__all__ = ["ComplianceNotificationService"]
