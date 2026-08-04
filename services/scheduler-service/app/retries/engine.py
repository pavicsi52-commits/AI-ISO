"""Retry delay computation and dead-letter eligibility.

**Reuses ``shared_core.queue.retry.compute_backoff_delay`` directly**
for the ``EXPONENTIAL_BACKOFF`` case, rather than reimplementing
exponential backoff a further time in this repository. ``FIXED`` is the
same function with its multiplier pinned to ``1.0`` -- a constant delay
is exactly what an exponential curve with no growth produces, not a
separate formula. ``LINEAR_BACKOFF`` is genuinely absent from the shared
framework (which implements only exponential and, by extension, fixed),
so it is this module's one real addition.
"""

from __future__ import annotations

import random

from shared_core.queue.retry import compute_backoff_delay

from app.models.enums import RetryType


def compute_delay_seconds(
    retry_type: RetryType,
    attempt: int,
    *,
    base_seconds: float,
    max_seconds: float,
) -> float:
    """The delay before *attempt* (1-indexed: 1 is the first retry).

    Every delay includes the same jitter
    :func:`~shared_core.queue.retry.compute_backoff_delay` already adds
    for ``EXPONENTIAL_BACKOFF`` and, by the ``multiplier=1.0`` identity
    above, ``FIXED`` -- jitter is what keeps a fleet of jobs that all
    failed at once from retrying in the same synchronized burst a second
    time. ``LINEAR_BACKOFF`` adds the same style of jitter directly.
    """
    if retry_type is RetryType.FIXED:
        return compute_backoff_delay(
            attempt, base_seconds=base_seconds, max_seconds=max_seconds, multiplier=1.0
        )
    if retry_type is RetryType.LINEAR_BACKOFF:
        delay = min(base_seconds * attempt, max_seconds)
        return delay + random.uniform(0, base_seconds)
    # EXPONENTIAL_BACKOFF and CUSTOM (whose customisation is in *which*
    # failures qualify, via retry_conditions, not a fourth delay curve).
    return compute_backoff_delay(attempt, base_seconds=base_seconds, max_seconds=max_seconds)


def should_retry(
    *,
    attempt_number: int,
    max_attempts: int,
    exit_code: int | None,
    error_message: str | None,
    retry_conditions: dict[str, object],
) -> bool:
    """Whether a failed execution should be retried at all.

    Empty *retry_conditions* means "retry on any failure," the
    permissive default `shared_core.queue.retry.is_retryable` also
    chooses for the same reason: a scheduler has no way to know a
    downstream job's own failure is safely retryable or not unless the
    caller says so.
    """
    if attempt_number >= max_attempts:
        return False

    exit_codes = retry_conditions.get("exit_codes")
    if isinstance(exit_codes, list) and exit_codes and exit_code not in exit_codes:
        return False

    error_patterns = retry_conditions.get("error_patterns")
    if isinstance(error_patterns, list) and error_patterns:
        if error_message is None:
            return False
        if not any(str(pattern) in error_message for pattern in error_patterns):
            return False

    return True


def is_dead_letter(*, attempt_number: int, max_attempts: int, dead_letter_enabled: bool) -> bool:
    """Whether a failure has exhausted its retries and should be routed to the dead letter."""
    return dead_letter_enabled and attempt_number >= max_attempts


__all__ = ["compute_delay_seconds", "is_dead_letter", "should_retry"]
