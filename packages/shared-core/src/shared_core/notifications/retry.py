"""Retry and dead letter.

Per docs/025_Enterprise_Notification_Framework.md.txt "RETRY": Retry
Policy, Exponential Backoff, Maximum Attempts, Failure Classification,
Dead Letter, Manual Retry. Reuses
:class:`shared_core.queue.retry.RetryPolicy`/:func:`~shared_core.queue
.retry.compute_backoff_delay` directly rather than reimplementing
exponential backoff a third time (queue, events, and now notifications).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime

from shared_core.notifications.channels import NotificationMessage
from shared_core.notifications.constants import DEFAULT_RETRY_MAX_ATTEMPTS
from shared_core.notifications.delivery import DeliveryResult, DeliveryStatus
from shared_core.queue.retry import RetryPolicy, compute_backoff_delay

_NON_RETRYABLE_STATUSES = frozenset({DeliveryStatus.CANCELLED, DeliveryStatus.EXPIRED})


def notification_retry_policy(*, max_attempts: int = DEFAULT_RETRY_MAX_ATTEMPTS) -> RetryPolicy:
    """The default :class:`RetryPolicy` for notification delivery."""
    return RetryPolicy(max_attempts=max_attempts)


def classify_delivery_failure(result: DeliveryResult) -> bool:
    """Whether a failed :class:`DeliveryResult` is worth retrying ("Failure Classification").

    A cancelled or expired notification should never be retried (the
    recipient no longer wants it, or the window to deliver it has
    passed); every other failure status is treated as transient.
    """
    if result.status not in (DeliveryStatus.FAILED, *_NON_RETRYABLE_STATUSES):
        return False
    return result.status not in _NON_RETRYABLE_STATUSES


@dataclass(frozen=True, slots=True)
class DeadLetteredNotification:
    """One notification that exhausted its retry policy."""

    message: NotificationMessage
    last_result: DeliveryResult
    attempts: int
    dead_lettered_at: datetime = field(default_factory=lambda: datetime.now(UTC))


class DeadLetterStore:
    """An in-memory store of notifications that exhausted retry ("Dead Letter"/"Manual Retry")."""

    def __init__(self) -> None:
        self._entries: list[DeadLetteredNotification] = []

    def add(
        self, message: NotificationMessage, *, last_result: DeliveryResult, attempts: int
    ) -> None:
        """Record *message* as dead-lettered."""
        self._entries.append(
            DeadLetteredNotification(message=message, last_result=last_result, attempts=attempts)
        )

    def all(self) -> list[DeadLetteredNotification]:
        """Every currently dead-lettered notification."""
        return list(self._entries)

    def pop_for_manual_retry(self, notification_id: str) -> NotificationMessage | None:
        """Remove and return *notification_id*'s message for a manual retry ("Manual Retry")."""
        for index, entry in enumerate(self._entries):
            if entry.message.notification_id == notification_id:
                del self._entries[index]
                return entry.message
        return None


__all__ = [
    "DeadLetterStore",
    "DeadLetteredNotification",
    "RetryPolicy",
    "classify_delivery_failure",
    "compute_backoff_delay",
    "notification_retry_policy",
]
