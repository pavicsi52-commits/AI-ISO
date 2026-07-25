"""Retry.

Per docs/021_Enterprise_Queue_Framework.md.txt "RETRY POLICY": Exponential
Backoff, Maximum Attempts, Retry Delay, Retry Classification, Retry
Metrics, Configurable.
"""

from __future__ import annotations

import random
from collections.abc import Callable
from dataclasses import dataclass, field

from shared_core.queue.constants import (
    DEFAULT_RETRY_BACKOFF_BASE_SECONDS,
    DEFAULT_RETRY_BACKOFF_MAX_SECONDS,
    DEFAULT_RETRY_BACKOFF_MULTIPLIER,
    DEFAULT_RETRY_MAX_ATTEMPTS,
)


def compute_backoff_delay(
    attempt: int,
    *,
    base_seconds: float = DEFAULT_RETRY_BACKOFF_BASE_SECONDS,
    max_seconds: float = DEFAULT_RETRY_BACKOFF_MAX_SECONDS,
    multiplier: float = DEFAULT_RETRY_BACKOFF_MULTIPLIER,
) -> float:
    """Compute an exponential-backoff delay (with jitter) for the given attempt number.

    *attempt* is 1-indexed: attempt 1 is the first retry after the
    original failed try.
    """
    delay = min(base_seconds * (multiplier ** (attempt - 1)), max_seconds)
    return delay + random.uniform(0, base_seconds)


def compute_backoff_delay_ms(
    attempt: int,
    *,
    base_seconds: float = DEFAULT_RETRY_BACKOFF_BASE_SECONDS,
    max_seconds: float = DEFAULT_RETRY_BACKOFF_MAX_SECONDS,
    multiplier: float = DEFAULT_RETRY_BACKOFF_MULTIPLIER,
) -> int:
    """Compute an exponential-backoff delay in whole seconds, as milliseconds, with no jitter.

    Used specifically for :mod:`shared_core.queue.delay`-backed retry
    requeuing, where the delay value becomes part of a holding queue's
    *name* -- jitter (as :func:`compute_backoff_delay` adds) would create
    a new, never-reused queue for nearly every retry. Rounding to whole
    seconds bounds the number of distinct holding queues the retry
    mechanism will ever create to ``max_seconds`` at most, all reused
    indefinitely across every retrying message in the system.
    """
    delay_seconds = min(base_seconds * (multiplier ** (attempt - 1)), max_seconds)
    return round(delay_seconds) * 1000


def is_retryable(exc: BaseException) -> bool:
    """Classify whether *exc* represents a failure worth retrying ("Retry Classification").

    Defaults to permissive -- retry anything -- since a generic queue
    consumer's handler is arbitrary business logic the framework has no
    way to know is safely retryable or not; a handler that wants to opt
    a specific failure *out* of retry (e.g. a validation error that will
    never succeed no matter how many attempts) raises an exception
    carrying an explicit ``retryable = False`` attribute (as every
    :class:`~shared_core.exceptions.base.AIIOSException` subclass
    already does), which this always honors.
    """
    retryable_attr = getattr(exc, "retryable", None)
    if retryable_attr is not None:
        return bool(retryable_attr)
    return True


@dataclass(frozen=True, slots=True)
class RetryPolicy:
    """How a consumer's handler failures are retried before dead-lettering ("Configurable")."""

    max_attempts: int = DEFAULT_RETRY_MAX_ATTEMPTS
    backoff_base_seconds: float = DEFAULT_RETRY_BACKOFF_BASE_SECONDS
    backoff_max_seconds: float = DEFAULT_RETRY_BACKOFF_MAX_SECONDS
    backoff_multiplier: float = DEFAULT_RETRY_BACKOFF_MULTIPLIER
    classify: Callable[[BaseException], bool] = field(default=is_retryable)

    def delay_for(self, attempt: int) -> float:
        """Compute the backoff delay for *attempt* under this policy."""
        return compute_backoff_delay(
            attempt,
            base_seconds=self.backoff_base_seconds,
            max_seconds=self.backoff_max_seconds,
            multiplier=self.backoff_multiplier,
        )


__all__ = ["RetryPolicy", "compute_backoff_delay", "compute_backoff_delay_ms", "is_retryable"]
