"""Retry policy.

Per docs/026_Enterprise_Scheduler_Framework.md.txt "RETRY POLICY":
Immediate Retry, Fixed Delay, Exponential Backoff, Maximum Attempts,
Retry Timeout, Retry Classification, Dead Letter Queue Integration.
Reuses :class:`shared_core.queue.retry.RetryPolicy`/
:func:`~shared_core.queue.retry.compute_backoff_delay`/
:func:`~shared_core.queue.retry.is_retryable` directly rather than
reimplementing exponential backoff a fourth time (queue, events,
notifications, and now scheduler). "Dead Letter Queue Integration" is
:mod:`shared_core.scheduler.queue`'s concern (the actual RabbitMQ
integration), not this module's.
"""

from __future__ import annotations

from shared_core.queue.retry import RetryPolicy, compute_backoff_delay, is_retryable
from shared_core.scheduler.constants import DEFAULT_RETRY_MAX_ATTEMPTS


def job_retry_policy(*, max_attempts: int = DEFAULT_RETRY_MAX_ATTEMPTS) -> RetryPolicy:
    """The default :class:`RetryPolicy` for job execution.

    ``max_attempts=0`` gives "Immediate Retry" semantics no differently
    than any other value -- the *first* attempt is never a retry;
    what makes retry "immediate" is a zero (or near-zero)
    ``backoff_base_seconds``, which the default `RetryPolicy` already
    supports directly via its own constructor.
    """
    return RetryPolicy(max_attempts=max_attempts)


__all__ = ["RetryPolicy", "compute_backoff_delay", "is_retryable", "job_retry_policy"]
