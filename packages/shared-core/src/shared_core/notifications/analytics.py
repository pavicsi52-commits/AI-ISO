"""Notification analytics.

Per docs/025_Enterprise_Notification_Framework.md.txt "ANALYTICS":
Sent, Delivered, Failed, Opened, Clicked, Bounced, Retried, Latency,
Channel Usage. Purely in-process, computed from
:class:`~shared_core.notifications.history.HistoryStore` and
:class:`~shared_core.notifications.tracking.TrackingRecorder` -- the
same "no business/persistence tables" stance as every prior framework's
own analytics (Prompt 023's ``monitoring.availability``, Prompt 024's
``telemetry.analytics``).
"""

from __future__ import annotations

from collections import Counter

from shared_core.enums.notification_channel import NotificationChannel
from shared_core.notifications.delivery import DeliveryStatus
from shared_core.notifications.history import HistoryStore
from shared_core.notifications.tracking import TrackingRecorder

_BOUNCE_MARKER = "bounce"


class NotificationAnalytics:
    """Computes docs/025 "ANALYTICS" figures from retained history and tracking events."""

    def __init__(self, *, history: HistoryStore, tracking: TrackingRecorder):
        self._history = history
        self._tracking = tracking

    def sent_count(self) -> int:
        """Notifications that reached ``SENT`` or ``DELIVERED`` on their latest attempt ("Sent")."""
        return sum(
            1
            for entry in self._history.entries()
            if entry.result.status in (DeliveryStatus.SENT, DeliveryStatus.DELIVERED)
        )

    def delivered_count(self) -> int:
        """Notifications confirmed ``DELIVERED`` ("Delivered")."""
        return sum(
            1
            for entry in self._history.entries()
            if entry.result.status == DeliveryStatus.DELIVERED
        )

    def failed_count(self) -> int:
        """Delivery attempts that ended in ``FAILED`` ("Failed")."""
        return sum(
            1 for entry in self._history.entries() if entry.result.status == DeliveryStatus.FAILED
        )

    def bounced_count(self) -> int:
        """Delivery attempts whose error indicates a bounce ("Bounced").

        A bounce is provider-reported, not a distinct
        :class:`~shared_core.notifications.delivery.DeliveryStatus`
        value -- detected here by the channel's own error text, the same
        signal a real provider integration would parse more precisely.
        """
        return sum(
            1
            for entry in self._history.entries()
            if entry.result.error is not None and _BOUNCE_MARKER in entry.result.error.lower()
        )

    def retried_count(self) -> int:
        """Delivery attempts beyond the first for their notification ("Retried")."""
        return sum(1 for entry in self._history.entries() if entry.attempt > 1)

    def opened_count(self) -> int:
        """Notifications opened ("Opened")."""
        return sum(1 for event in self._tracking.all_events() if event.kind == "open")

    def clicked_count(self) -> int:
        """Notification links clicked ("Clicked")."""
        return sum(1 for event in self._tracking.all_events() if event.kind == "click")

    def average_latency_ms(self, *, channel: NotificationChannel | None = None) -> float:
        """Average recorded delivery latency, in ms ("Latency"). ``0.0`` if none recorded."""
        latencies = [
            entry.result.latency_ms
            for entry in self._history.entries()
            if entry.result.latency_ms is not None
            and (channel is None or entry.result.channel == channel)
        ]
        if not latencies:
            return 0.0
        return sum(latencies) / len(latencies)

    def channel_usage(self) -> dict[NotificationChannel, int]:
        """How many delivery attempts each channel handled ("Channel Usage")."""
        return dict(Counter(entry.result.channel for entry in self._history.entries()))


__all__ = ["NotificationAnalytics"]
