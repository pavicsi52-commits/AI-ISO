"""Retry.

Per docs/020_Enterprise_Event_Framework.md.txt "RETRY": Exponential
Backoff, Maximum Attempts, Retry Delay, Retry Metrics, Retry
Classification.

:meth:`shared_core.queue.manager.QueueManager.consume` already retries a
failed handler up to ``max_retries`` times (by immediately re-publishing
with an incremented count header) before dead-lettering -- but with no
delay at all between attempts. This module adds the missing exponential
backoff *on top of* that existing count-based mechanism (a handler wrapper
sleeps before re-raising, so the queue's own retry/dead-letter bookkeeping
still does the actual requeue), rather than reimplementing retry/dead-letter
routing that :mod:`shared_core.queue` already owns.
"""

from __future__ import annotations

import random
from collections.abc import Callable
from dataclasses import dataclass, field

from shared_core.events.constants import (
    DEFAULT_RETRY_BACKOFF_BASE_SECONDS,
    DEFAULT_RETRY_BACKOFF_MAX_SECONDS,
    DEFAULT_RETRY_MAX_ATTEMPTS,
)


def compute_backoff_delay(
    attempt: int,
    *,
    base_seconds: float = DEFAULT_RETRY_BACKOFF_BASE_SECONDS,
    max_seconds: float = DEFAULT_RETRY_BACKOFF_MAX_SECONDS,
) -> float:
    """Compute an exponential-backoff delay (with jitter) for the given attempt number.

    *attempt* is 1-indexed: attempt 1 is the first retry after the
    original failed try.
    """
    delay = min(base_seconds * (2.0 ** (attempt - 1)), max_seconds)
    return delay + random.uniform(0, base_seconds)


def is_retryable(exc: BaseException) -> bool:
    """Classify whether *exc* represents a transient failure worth retrying.

    Framework exceptions (:class:`~shared_core.exceptions.event.EventError`
    and subclasses) already carry a ``retryable`` flag (docs/015); for
    anything else, connection/timeout errors are treated as transient and
    everything else is not.
    """
    retryable_attr = getattr(exc, "retryable", None)
    if retryable_attr is not None:
        return bool(retryable_attr)
    return isinstance(exc, (ConnectionError, TimeoutError, OSError))


@dataclass(frozen=True, slots=True)
class RetryPolicy:
    """How a subscriber's handler failures are retried before dead-lettering."""

    max_attempts: int = DEFAULT_RETRY_MAX_ATTEMPTS
    backoff_base_seconds: float = DEFAULT_RETRY_BACKOFF_BASE_SECONDS
    backoff_max_seconds: float = DEFAULT_RETRY_BACKOFF_MAX_SECONDS
    classify: Callable[[BaseException], bool] = field(default=is_retryable)

    def delay_for(self, attempt: int) -> float:
        """Compute the backoff delay for *attempt* under this policy."""
        return compute_backoff_delay(
            attempt, base_seconds=self.backoff_base_seconds, max_seconds=self.backoff_max_seconds
        )


__all__ = ["RetryPolicy", "compute_backoff_delay", "is_retryable"]
