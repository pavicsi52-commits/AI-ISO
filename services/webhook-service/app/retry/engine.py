"""Retry backoff computation (docs/057 "RETRY MANAGEMENT").

``EXPONENTIAL`` delegates to `shared_core.queue.retry.compute_backoff_delay`
directly (jittered exponential backoff, already implemented and already
reused by every prior service with a retry sweep). ``LINEAR`` is a
genuine gap -- `shared_core` supports only exponential backoff -- built
new to match.
"""

from __future__ import annotations

from shared_core.queue.retry import compute_backoff_delay

from app.models.enums import RetryBackoffStrategy


def compute_linear_delay(attempt: int, *, base_seconds: float, max_seconds: float) -> float:
    """The *attempt*-th linear backoff delay: ``base_seconds * attempt``, capped."""
    return min(base_seconds * attempt, max_seconds)


def compute_delay(
    attempt: int,
    *,
    strategy: RetryBackoffStrategy,
    base_seconds: float,
    max_seconds: float,
) -> float:
    """The delay before retry attempt number *attempt*, under *strategy*."""
    if strategy == RetryBackoffStrategy.LINEAR:
        return compute_linear_delay(attempt, base_seconds=base_seconds, max_seconds=max_seconds)
    return compute_backoff_delay(attempt, base_seconds=base_seconds, max_seconds=max_seconds)


def has_attempts_remaining(attempt_count: int, *, max_attempts: int) -> bool:
    """Whether another retry attempt is still allowed."""
    return attempt_count < max_attempts


__all__ = ["compute_delay", "compute_linear_delay", "has_attempts_remaining"]
