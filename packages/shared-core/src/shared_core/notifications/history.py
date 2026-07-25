"""Delivery history.

Per docs/025_Enterprise_Notification_Framework.md.txt "DELIVERY" and
"ANALYTICS": a record of every delivery attempt, feeding
:mod:`shared_core.notifications.analytics`. Purely in-process, the same
"no business/persistence tables" stance as every prior framework's own
state -- a real service wanting delivery history surviving a restart
persists it in its own database, keyed off the same
:class:`~shared_core.notifications.delivery.DeliveryResult` this store
already records.
"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass

from shared_core.enums.notification_channel import NotificationChannel
from shared_core.notifications.constants import DEFAULT_HISTORY_BUFFER_SIZE
from shared_core.notifications.delivery import DeliveryResult, DeliveryStatus


@dataclass(frozen=True, slots=True)
class HistoryEntry:
    """One recorded delivery attempt."""

    notification_id: str
    attempt: int
    result: DeliveryResult


class HistoryStore:
    """A bounded, in-memory buffer of recent delivery attempts."""

    def __init__(self, *, max_size: int = DEFAULT_HISTORY_BUFFER_SIZE):
        self._entries: deque[HistoryEntry] = deque(maxlen=max_size)

    def record(self, notification_id: str, *, attempt: int, result: DeliveryResult) -> None:
        """Record one delivery attempt's outcome."""
        self._entries.append(
            HistoryEntry(notification_id=notification_id, attempt=attempt, result=result)
        )

    def entries(self) -> list[HistoryEntry]:
        """Every currently retained entry, oldest first."""
        return list(self._entries)

    def for_notification(self, notification_id: str) -> list[HistoryEntry]:
        """Every retained attempt for *notification_id*, in attempt order."""
        return [entry for entry in self._entries if entry.notification_id == notification_id]

    def latest_status(self, notification_id: str) -> DeliveryStatus | None:
        """The most recent status recorded for *notification_id*, if any."""
        matches = self.for_notification(notification_id)
        return matches[-1].result.status if matches else None

    def by_channel(self, channel: NotificationChannel) -> list[HistoryEntry]:
        """Every retained entry delivered (or attempted) over *channel*."""
        return [entry for entry in self._entries if entry.result.channel == channel]


__all__ = ["HistoryEntry", "HistoryStore"]
