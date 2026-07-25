"""Retry-with-backoff helper."""

from __future__ import annotations

import asyncio
import random
from collections.abc import Awaitable, Callable


async def retry_async[T](
    func: Callable[[], Awaitable[T]],
    *,
    max_attempts: int = 3,
    initial_delay_seconds: float = 1.0,
    backoff_multiplier: float = 2.0,
    retryable_exceptions: tuple[type[Exception], ...] = (Exception,),
    jitter: bool = True,
) -> T:
    """Call ``func`` with exponential-backoff retry.

    Args:
        func: Zero-argument async callable to invoke.
        max_attempts: Maximum number of attempts before giving up. Must be >= 1.
        initial_delay_seconds: Delay before the first retry.
        backoff_multiplier: Multiplier applied to the delay after each attempt.
        retryable_exceptions: Exception types that trigger a retry.
        jitter: Whether to add random jitter (0-25%) to each delay.

    Returns:
        The result of ``func()``.

    Raises:
        ValueError: If ``max_attempts`` is less than 1.
        Exception: The last exception raised by ``func``, if all attempts fail.
    """
    if max_attempts < 1:
        raise ValueError("max_attempts must be >= 1")

    delay = initial_delay_seconds

    for attempt in range(1, max_attempts + 1):
        try:
            return await func()
        except retryable_exceptions:
            if attempt == max_attempts:
                raise
            sleep_for = delay * (1 + random.random() * 0.25) if jitter else delay
            await asyncio.sleep(sleep_for)
            delay *= backoff_multiplier

    raise RuntimeError("unreachable")  # pragma: no cover
