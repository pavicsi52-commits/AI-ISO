"""Elapsed-time measurement helpers."""

from __future__ import annotations

import time
from collections.abc import Iterator
from contextlib import contextmanager


class Stopwatch:
    """Measures elapsed wall-clock time in milliseconds."""

    def __init__(self) -> None:
        self._start = time.perf_counter()

    def elapsed_ms(self) -> float:
        """Return elapsed time in milliseconds since construction."""
        return (time.perf_counter() - self._start) * 1000

    def reset(self) -> None:
        """Restart the stopwatch."""
        self._start = time.perf_counter()


@contextmanager
def measure_ms() -> Iterator[Stopwatch]:
    """Context manager yielding a running :class:`Stopwatch`."""
    stopwatch = Stopwatch()
    yield stopwatch
