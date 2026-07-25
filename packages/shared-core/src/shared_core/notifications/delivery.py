"""Delivery status, mode, and result.

Per docs/025_Enterprise_Notification_Framework.md.txt "DELIVERY" and
"DELIVERY STATUS".
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum

from shared_core.enums.notification_channel import NotificationChannel


class DeliveryStatus(StrEnum):
    """Every status a notification passes through, per docs/025 "DELIVERY STATUS"."""

    PENDING = "pending"
    QUEUED = "queued"
    SENDING = "sending"
    SENT = "sent"
    DELIVERED = "delivered"
    READ = "read"
    FAILED = "failed"
    EXPIRED = "expired"
    CANCELLED = "cancelled"


class DeliveryMode(StrEnum):
    """Every delivery mode docs/025 "DELIVERY" names."""

    IMMEDIATE = "immediate"
    SCHEDULED = "scheduled"
    RECURRING = "recurring"
    DELAYED = "delayed"
    BULK = "bulk"
    BROADCAST = "broadcast"
    MULTICAST = "multicast"


@dataclass(frozen=True, slots=True)
class DeliveryResult:
    """The outcome of one channel's attempt to deliver one notification."""

    status: DeliveryStatus
    channel: NotificationChannel
    completed_at: datetime
    provider_message_id: str | None = None
    error: str | None = None
    latency_ms: float | None = None


def build_delivery_result(
    *,
    status: DeliveryStatus,
    channel: NotificationChannel,
    provider_message_id: str | None = None,
    error: str | None = None,
    latency_ms: float | None = None,
) -> DeliveryResult:
    """Build a :class:`DeliveryResult` timestamped at the current moment."""
    return DeliveryResult(
        status=status,
        channel=channel,
        completed_at=datetime.now(UTC),
        provider_message_id=provider_message_id,
        error=error,
        latency_ms=latency_ms,
    )


__all__ = ["DeliveryMode", "DeliveryResult", "DeliveryStatus", "build_delivery_result"]
