"""Application monitoring.

Per docs/023_Enterprise_Monitoring_Framework.md.txt "APPLICATION
MONITORING": CPU Usage, Memory Usage, Response Time, Request Count,
Error Count, Exception Count, Open Connections, Thread Count, Garbage
Collection, Event Loop Delay.
"""

from __future__ import annotations

import asyncio
import gc
import time
from collections import deque
from dataclasses import dataclass, field

import psutil

from shared_core.monitoring.constants import (
    DEFAULT_EVENT_LOOP_DELAY_SAMPLE_SECONDS,
    DEFAULT_RESPONSE_TIME_SAMPLE_WINDOW,
)

_process = psutil.Process()


@dataclass(frozen=True, slots=True)
class GarbageCollectionStats:
    """Per-generation GC collection counts ("Garbage Collection")."""

    collections: tuple[int, ...]
    collected: tuple[int, ...]
    uncollectable: tuple[int, ...]


@dataclass(frozen=True, slots=True)
class ApplicationSnapshot:
    """A point-in-time snapshot of this process's own resource usage."""

    cpu_percent: float
    memory_rss_bytes: int
    memory_percent: float
    thread_count: int
    open_file_count: int
    garbage_collection: GarbageCollectionStats


def capture_application_snapshot() -> ApplicationSnapshot:
    """Capture CPU/memory/thread/open-file/GC state for the current process."""
    with _process.oneshot():
        cpu_percent = _process.cpu_percent(interval=None)
        memory_info = _process.memory_info()
        memory_percent = _process.memory_percent()
        thread_count = _process.num_threads()
        try:
            open_file_count = len(_process.open_files())
        except psutil.Error:
            open_file_count = 0
    stats = gc.get_stats()
    return ApplicationSnapshot(
        cpu_percent=cpu_percent,
        memory_rss_bytes=memory_info.rss,
        memory_percent=memory_percent,
        thread_count=thread_count,
        open_file_count=open_file_count,
        garbage_collection=GarbageCollectionStats(
            collections=tuple(int(s["collections"]) for s in stats),
            collected=tuple(int(s["collected"]) for s in stats),
            uncollectable=tuple(int(s["uncollectable"]) for s in stats),
        ),
    )


async def measure_event_loop_delay(
    *, sample_seconds: float = DEFAULT_EVENT_LOOP_DELAY_SAMPLE_SECONDS
) -> float:
    """Measure the running event loop's scheduling delay, in seconds ("Event Loop Delay").

    Schedules a sleep for *sample_seconds* and measures how much longer
    than that it actually took -- the excess is time the loop spent on
    other work before getting back to this coroutine.
    """
    start = time.monotonic()
    await asyncio.sleep(sample_seconds)
    elapsed = time.monotonic() - start
    return max(0.0, elapsed - sample_seconds)


@dataclass(slots=True)
class ApplicationStatistics:
    """Rolling in-process counters: Response Time, Request/Error/Exception/Warning Count."""

    request_count: int = 0
    error_count: int = 0
    exception_count: int = 0
    warning_count: int = 0
    _response_times_ms: deque[float] = field(
        default_factory=lambda: deque(maxlen=DEFAULT_RESPONSE_TIME_SAMPLE_WINDOW)
    )

    def record_request(self, response_time_ms: float) -> None:
        """Record one completed request and its response time ("Response Time"/"Request Count")."""
        self.request_count += 1
        self._response_times_ms.append(response_time_ms)

    def record_error(self) -> None:
        """Record one request-level error ("Error Count")."""
        self.error_count += 1

    def record_exception(self) -> None:
        """Record one unhandled exception ("Exception Count")."""
        self.exception_count += 1

    def record_warning(self) -> None:
        """Record one application warning ("Warnings")."""
        self.warning_count += 1

    @property
    def average_response_time_ms(self) -> float:
        """Average response time over the retained sample window. ``0.0`` if no requests yet."""
        if not self._response_times_ms:
            return 0.0
        return sum(self._response_times_ms) / len(self._response_times_ms)

    @property
    def error_rate(self) -> float:
        """Fraction of requests that errored, in ``[0.0, 1.0]``. ``0.0`` if no requests yet."""
        if not self.request_count:
            return 0.0
        return self.error_count / self.request_count

    def reset(self) -> None:
        """Zero every counter and clear the response-time sample window."""
        self.request_count = 0
        self.error_count = 0
        self.exception_count = 0
        self.warning_count = 0
        self._response_times_ms.clear()


__all__ = [
    "ApplicationSnapshot",
    "ApplicationStatistics",
    "GarbageCollectionStats",
    "capture_application_snapshot",
    "measure_event_loop_delay",
]
