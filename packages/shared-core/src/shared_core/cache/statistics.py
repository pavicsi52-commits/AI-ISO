"""In-process cache statistics.

Per docs/019_Enterprise_Cache_Framework.md.txt "METRICS": Cache Hits,
Cache Misses, Hit Ratio, Miss Ratio, Operations Per Second. This module is
the lightweight, always-on tracker every
:class:`~shared_core.cache.manager.CacheManager` carries;
:mod:`shared_core.cache.metrics` is the Prometheus exposition layer that
reads Redis ``INFO`` for the server-side counters (memory, evictions,
connections) this in-process tracker cannot see.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field


@dataclass(slots=True)
class CacheStatistics:
    """Rolling in-process counters for one :class:`CacheManager` instance."""

    hits: int = 0
    misses: int = 0
    sets: int = 0
    deletes: int = 0
    errors: int = 0
    started_at: float = field(default_factory=time.monotonic)

    def record_hit(self) -> None:
        """Record a cache read that found a value."""
        self.hits += 1

    def record_miss(self) -> None:
        """Record a cache read that found nothing."""
        self.misses += 1

    def record_set(self) -> None:
        """Record a cache write."""
        self.sets += 1

    def record_delete(self) -> None:
        """Record a cache deletion."""
        self.deletes += 1

    def record_error(self) -> None:
        """Record a failed cache operation (connection/serialization/etc.)."""
        self.errors += 1

    @property
    def total_reads(self) -> int:
        """Total number of ``get``-style operations recorded."""
        return self.hits + self.misses

    @property
    def hit_ratio(self) -> float:
        """Fraction of reads that were hits, in ``[0.0, 1.0]``. ``0.0`` if no reads yet."""
        total = self.total_reads
        return self.hits / total if total else 0.0

    @property
    def miss_ratio(self) -> float:
        """Fraction of reads that were misses, in ``[0.0, 1.0]``. ``0.0`` if no reads yet."""
        total = self.total_reads
        return self.misses / total if total else 0.0

    @property
    def uptime_seconds(self) -> float:
        """Seconds since this tracker was created (or last :meth:`reset`)."""
        return time.monotonic() - self.started_at

    @property
    def operations_per_second(self) -> float:
        """Average operation rate (reads + writes + deletes) over this tracker's lifetime."""
        uptime = self.uptime_seconds
        if uptime <= 0:
            return 0.0
        return (self.hits + self.misses + self.sets + self.deletes) / uptime

    def reset(self) -> None:
        """Zero every counter and restart the uptime clock."""
        self.hits = 0
        self.misses = 0
        self.sets = 0
        self.deletes = 0
        self.errors = 0
        self.started_at = time.monotonic()


__all__ = ["CacheStatistics"]
