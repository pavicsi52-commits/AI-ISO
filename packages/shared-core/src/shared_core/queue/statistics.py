"""In-process queue statistics.

Per docs/021_Enterprise_Queue_Framework.md.txt "METRICS": Published,
Consumed, Failed, Retried, Dead Letter, Throughput. This module is the
lightweight, always-on tracker every
:class:`~shared_core.queue.manager.QueueManager` carries;
:mod:`shared_core.queue.metrics` is the Prometheus exposition layer.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field


@dataclass(slots=True)
class QueueStatistics:
    """Rolling in-process counters for one :class:`QueueManager` instance."""

    published: int = 0
    consumed: int = 0
    failed: int = 0
    retried: int = 0
    dead_lettered: int = 0
    started_at: float = field(default_factory=time.monotonic)

    def record_published(self) -> None:
        """Record a message published."""
        self.published += 1

    def record_consumed(self) -> None:
        """Record a message successfully handled."""
        self.consumed += 1

    def record_failed(self) -> None:
        """Record a handler failure (whether or not it's later retried)."""
        self.failed += 1

    def record_retried(self) -> None:
        """Record a message requeued for another attempt."""
        self.retried += 1

    def record_dead_lettered(self) -> None:
        """Record a message that exhausted its retries and was dead-lettered."""
        self.dead_lettered += 1

    @property
    def uptime_seconds(self) -> float:
        """Seconds since this tracker was created (or last :meth:`reset`)."""
        return time.monotonic() - self.started_at

    @property
    def publish_throughput_per_second(self) -> float:
        """Average publish rate over this tracker's lifetime."""
        uptime = self.uptime_seconds
        return self.published / uptime if uptime > 0 else 0.0

    @property
    def consume_throughput_per_second(self) -> float:
        """Average consume rate over this tracker's lifetime."""
        uptime = self.uptime_seconds
        return self.consumed / uptime if uptime > 0 else 0.0

    @property
    def failure_ratio(self) -> float:
        """Fraction of consume attempts that failed, in ``[0.0, 1.0]``. ``0.0`` if none yet."""
        total = self.consumed + self.failed
        return self.failed / total if total else 0.0

    def reset(self) -> None:
        """Zero every counter and restart the uptime clock."""
        self.published = 0
        self.consumed = 0
        self.failed = 0
        self.retried = 0
        self.dead_lettered = 0
        self.started_at = time.monotonic()


__all__ = ["QueueStatistics"]
