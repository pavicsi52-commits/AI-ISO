"""Notification framework health.

Per docs/025_Enterprise_Notification_Framework.md.txt "HEALTH": SMTP
Status, SMS Provider Status, Webhook Status, Slack Status, Teams Status,
Push Status, Queue Status. Reuses
:func:`shared_core.monitoring.checks.check_tcp_reachable`/
:func:`~shared_core.monitoring.checks.check_http_reachable` and
:func:`shared_core.monitoring.status.calculate_status` (Prompt 023)
rather than reimplementing connectivity checks or status rollup.
"""

from __future__ import annotations

from dataclasses import dataclass

from shared_core.enums.health_status import HealthStatus
from shared_core.enums.notification_channel import NotificationChannel
from shared_core.monitoring.checks import check_http_reachable, check_tcp_reachable
from shared_core.monitoring.status import calculate_status


@dataclass(frozen=True, slots=True)
class NotificationHealthReport:
    """A point-in-time snapshot of every configured channel's, and the queue's, health."""

    status: HealthStatus
    channel_statuses: dict[NotificationChannel, HealthStatus]
    queue_status: HealthStatus


async def check_smtp_health(host: str, port: int) -> HealthStatus:
    """Check SMTP connectivity ("SMTP Status")."""
    result = await check_tcp_reachable("smtp", host, port)
    return result.status


async def check_webhook_health(url: str) -> HealthStatus:
    """Check a webhook endpoint's reachability ("Webhook Status"/"Slack Status"/"Teams Status")."""
    result = await check_http_reachable("webhook", url)
    return result.status


async def check_http_provider_health(url: str) -> HealthStatus:
    """Check a generic HTTP provider's reachability ("SMS Provider Status"/"Push Status")."""
    result = await check_http_reachable("provider", url)
    return result.status


def calculate_notification_health(
    *,
    channel_statuses: dict[NotificationChannel, HealthStatus],
    queue_status: HealthStatus = HealthStatus.HEALTHY,
) -> NotificationHealthReport:
    """Build a :class:`NotificationHealthReport`, rolling up every channel and the queue."""
    overall = calculate_status([*channel_statuses.values(), queue_status])
    return NotificationHealthReport(
        status=overall, channel_statuses=channel_statuses, queue_status=queue_status
    )


__all__ = [
    "NotificationHealthReport",
    "calculate_notification_health",
    "check_http_provider_health",
    "check_smtp_health",
    "check_webhook_health",
]
