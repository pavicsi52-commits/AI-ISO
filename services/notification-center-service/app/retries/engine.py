"""Retry delay computation and dead-letter eligibility.

**Reuses `shared_core.queue.retry.compute_backoff_delay` and
`shared_core.notifications.retry.classify_delivery_failure` directly**,
the same exponential-backoff curve and failure classification every
prior AI-IOS retrying subsystem (queue, scheduler, and now notifications)
already shares -- this module only adds the attempt-count ceiling on top.
"""

from __future__ import annotations

from shared_core.notifications.delivery import DeliveryResult, DeliveryStatus
from shared_core.notifications.retry import classify_delivery_failure
from shared_core.queue.retry import compute_backoff_delay


def compute_delay_seconds(attempt: int, *, base_seconds: float, max_seconds: float) -> float:
    """The delay before *attempt* (1-indexed: 1 is the first retry)."""
    return compute_backoff_delay(attempt, base_seconds=base_seconds, max_seconds=max_seconds)


def should_retry(result: DeliveryResult, *, attempt_number: int, max_attempts: int) -> bool:
    """Whether a failed delivery is worth retrying again.

    Delegates failure classification to `shared_core` (a cancelled or
    expired notification is never retried) and only adds the
    attempt-count ceiling on top.
    """
    if attempt_number >= max_attempts:
        return False
    return classify_delivery_failure(result)


def is_dead_letter(result: DeliveryResult, *, attempt_number: int, max_attempts: int) -> bool:
    """Whether a failed delivery has exhausted its retries and belongs in the dead letter."""
    return result.status == DeliveryStatus.FAILED and attempt_number >= max_attempts


__all__ = ["compute_delay_seconds", "is_dead_letter", "should_retry"]
