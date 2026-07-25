"""Cache warmup.

Per docs/019_Enterprise_Cache_Framework.md.txt "CACHE WARMUP": Startup
Warmup, Scheduled Warmup. ("Predictive Warmup" is explicitly listed as
future work -- not implemented here.)
"""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field

from shared_core.cache.constants import DEFAULT_WARMUP_CONCURRENCY
from shared_core.cache.manager import CacheManager
from shared_core.logging import get_logger

logger = get_logger("shared_core.cache.warmup")

WarmupTask = Callable[[CacheManager], Awaitable[None]]


@dataclass(slots=True)
class WarmupRegistry:
    """Registry of cache-warming tasks, run concurrently (bounded) at startup or on a schedule.

    No concrete warmup data lives here -- that would be business logic;
    each service registers its own tasks (typically "load these hot keys
    from the database into the cache").
    """

    _tasks: list[WarmupTask] = field(default_factory=list)

    def register(self, task: WarmupTask) -> None:
        """Register *task* to run on the next :meth:`run`."""
        self._tasks.append(task)

    async def run(
        self, cache: CacheManager, *, concurrency: int = DEFAULT_WARMUP_CONCURRENCY
    ) -> int:
        """Run every registered task, at most *concurrency* running at once.

        A single failing task is logged and does not prevent the others
        from running -- warmup is a performance optimization, never a
        precondition for the service to serve traffic.
        """
        semaphore = asyncio.Semaphore(concurrency)

        async def _run_one(task: WarmupTask) -> None:
            async with semaphore:
                try:
                    await task(cache)
                except Exception:
                    logger.warning("cache warmup task failed", exc_info=True)

        await asyncio.gather(*(_run_one(task) for task in self._tasks))
        return len(self._tasks)


def warmup_task(registry: WarmupRegistry) -> Callable[[WarmupTask], WarmupTask]:
    """Decorator form of :meth:`WarmupRegistry.register`."""

    def decorator(task: WarmupTask) -> WarmupTask:
        registry.register(task)
        return task

    return decorator


__all__ = ["WarmupRegistry", "WarmupTask", "warmup_task"]
