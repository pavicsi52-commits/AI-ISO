"""Notification metrics.

Per docs/025_Enterprise_Notification_Framework.md.txt "ANALYTICS":
Sent, Delivered, Failed, Opened, Clicked, Bounced, Retried, Latency,
Channel Usage. Every one of these is genuinely new -- no prior prompt
defined notification-specific Prometheus instruments.
"""

from __future__ import annotations

from shared_core.enums.notification_channel import NotificationChannel
from shared_core.metrics.registry import create_counter, create_histogram

notifications_sent_total = create_counter(
    "notifications_sent_total", "Total notifications successfully sent.", labels=["channel"]
)
notifications_delivered_total = create_counter(
    "notifications_delivered_total", "Total notifications confirmed delivered.", labels=["channel"]
)
notifications_failed_total = create_counter(
    "notifications_failed_total", "Total notifications that failed delivery.", labels=["channel"]
)
notifications_opened_total = create_counter(
    "notifications_opened_total",
    "Total notifications opened by their recipient.",
    labels=["channel"],
)
notifications_clicked_total = create_counter(
    "notifications_clicked_total", "Total notification links clicked.", labels=["channel"]
)
notifications_bounced_total = create_counter(
    "notifications_bounced_total", "Total notifications that bounced.", labels=["channel"]
)
notifications_retried_total = create_counter(
    "notifications_retried_total", "Total notification delivery retries.", labels=["channel"]
)
notification_delivery_latency_seconds = create_histogram(
    "notification_delivery_latency_seconds",
    "Time spent delivering a notification, in seconds.",
    labels=["channel"],
)


def record_sent(channel: NotificationChannel) -> None:
    """Record one successfully sent notification ("Sent")."""
    notifications_sent_total.labels(channel=channel.value).inc()


def record_delivered(channel: NotificationChannel) -> None:
    """Record one confirmed-delivered notification ("Delivered")."""
    notifications_delivered_total.labels(channel=channel.value).inc()


def record_failed(channel: NotificationChannel) -> None:
    """Record one failed notification ("Failed")."""
    notifications_failed_total.labels(channel=channel.value).inc()


def record_opened(channel: NotificationChannel) -> None:
    """Record one notification open ("Opened")."""
    notifications_opened_total.labels(channel=channel.value).inc()


def record_clicked(channel: NotificationChannel) -> None:
    """Record one notification link click ("Clicked")."""
    notifications_clicked_total.labels(channel=channel.value).inc()


def record_bounced(channel: NotificationChannel) -> None:
    """Record one bounced notification ("Bounced")."""
    notifications_bounced_total.labels(channel=channel.value).inc()


def record_retried(channel: NotificationChannel) -> None:
    """Record one notification delivery retry ("Retried")."""
    notifications_retried_total.labels(channel=channel.value).inc()


def record_latency(channel: NotificationChannel, latency_ms: float) -> None:
    """Record one delivery attempt's latency, in seconds ("Latency")."""
    notification_delivery_latency_seconds.labels(channel=channel.value).observe(latency_ms / 1000)


__all__ = [
    "notification_delivery_latency_seconds",
    "notifications_bounced_total",
    "notifications_clicked_total",
    "notifications_delivered_total",
    "notifications_failed_total",
    "notifications_opened_total",
    "notifications_retried_total",
    "notifications_sent_total",
    "record_bounced",
    "record_clicked",
    "record_delivered",
    "record_failed",
    "record_latency",
    "record_opened",
    "record_retried",
    "record_sent",
]
