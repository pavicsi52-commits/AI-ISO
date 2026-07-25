"""Retry and circuit breaking.

Per docs/028_Enterprise_Workflow_SDK.md.txt "RETRY": Per Step, Per
Task, Per Workflow, Fixed Delay, Exponential Backoff, Maximum
Attempts, Circuit Breaker. Reuses
:class:`shared_core.queue.retry.RetryPolicy` (backoff/classification,
implemented once and now shared by queue, events, notifications,
scheduler, connectors, and workflow) and
:class:`shared_core.connectors.retry.CircuitBreaker` (the three-state
breaker Prompt 027 already built) directly rather than a
third/sixth reimplementation of either.
"""

from __future__ import annotations

from shared_core.connectors.retry import CircuitBreaker, CircuitState
from shared_core.queue.retry import RetryPolicy
from shared_core.workflow.constants import DEFAULT_RETRY_MAX_ATTEMPTS


def workflow_retry_policy(*, max_attempts: int = DEFAULT_RETRY_MAX_ATTEMPTS) -> RetryPolicy:
    """Build the default workflow :class:`RetryPolicy` ("Maximum Attempts")."""
    return RetryPolicy(max_attempts=max_attempts)


__all__ = ["CircuitBreaker", "CircuitState", "workflow_retry_policy"]
