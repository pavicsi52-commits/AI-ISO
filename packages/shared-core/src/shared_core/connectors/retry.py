"""Retry and circuit breaking.

Per docs/027_Enterprise_Connector_SDK.md.txt "RETRY": Immediate, Fixed
Delay, Exponential Backoff, Maximum Attempts, Retry Classification,
Circuit Breaker. Reuses :class:`shared_core.queue.retry.RetryPolicy`
directly (exponential backoff/classification implemented once, now
shared by queue, events, notifications, scheduler, and connectors)
rather than a fifth reimplementation. "Circuit Breaker" is genuinely
new -- nothing like it exists elsewhere in this monorepo.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from enum import StrEnum

from shared_core.connectors.constants import (
    DEFAULT_CIRCUIT_BREAKER_FAILURE_THRESHOLD,
    DEFAULT_CIRCUIT_BREAKER_RECOVERY_SECONDS,
    DEFAULT_RETRY_MAX_ATTEMPTS,
)
from shared_core.connectors.exceptions import CircuitBreakerOpenError
from shared_core.queue.retry import RetryPolicy


def connector_retry_policy(*, max_attempts: int = DEFAULT_RETRY_MAX_ATTEMPTS) -> RetryPolicy:
    """Build the default connector :class:`RetryPolicy` ("Maximum Attempts")."""
    return RetryPolicy(max_attempts=max_attempts)


class CircuitState(StrEnum):
    """A circuit breaker's own state machine."""

    CLOSED = "closed"
    OPEN = "open"
    HALF_OPEN = "half_open"


@dataclass(slots=True)
class CircuitBreaker:
    """Stops calling a consistently-failing target until it's had time to recover.

    CLOSED (normal) -> OPEN (after ``failure_threshold`` consecutive
    failures, rejects every call for ``recovery_seconds``) -> HALF_OPEN
    (one trial call is allowed through; success returns to CLOSED,
    failure returns to OPEN) -- the standard three-state circuit
    breaker.
    """

    failure_threshold: int = DEFAULT_CIRCUIT_BREAKER_FAILURE_THRESHOLD
    recovery_seconds: float = DEFAULT_CIRCUIT_BREAKER_RECOVERY_SECONDS
    _state: CircuitState = field(default=CircuitState.CLOSED, init=False)
    _consecutive_failures: int = field(default=0, init=False)
    _opened_at: float | None = field(default=None, init=False)

    @property
    def state(self) -> CircuitState:
        """This breaker's state, resolving OPEN -> HALF_OPEN once recovery has elapsed."""
        recovery_elapsed = (
            self._opened_at is not None
            and time.monotonic() - self._opened_at >= self.recovery_seconds
        )
        if self._state == CircuitState.OPEN and recovery_elapsed:
            return CircuitState.HALF_OPEN
        return self._state

    def before_call(self) -> None:
        """Check whether a call may proceed.

        Raises:
            CircuitBreakerOpenError: If the breaker is (still) open.
        """
        if self.state == CircuitState.OPEN:
            raise CircuitBreakerOpenError(
                f"Circuit breaker is open; retry after {self.recovery_seconds}s."
            )

    def record_success(self) -> None:
        """Record a successful call, closing the breaker."""
        self._consecutive_failures = 0
        self._state = CircuitState.CLOSED
        self._opened_at = None

    def record_failure(self) -> None:
        """Record a failed call, opening the breaker once ``failure_threshold`` is reached."""
        self._consecutive_failures += 1
        is_failed_trial = self.state == CircuitState.HALF_OPEN
        if is_failed_trial or self._consecutive_failures >= self.failure_threshold:
            self._state = CircuitState.OPEN
            self._opened_at = time.monotonic()


__all__ = ["CircuitBreaker", "CircuitState", "connector_retry_policy"]
