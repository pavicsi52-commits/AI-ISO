"""Background queue workers and worker pools.

Per docs/021_Enterprise_Queue_Framework.md.txt "WORKER POOL": Dynamic
Workers, Concurrency Control, Worker Health, Worker Restart, Worker
Shutdown, Worker Metrics.
"""

from __future__ import annotations

import asyncio
import time
from abc import ABC, abstractmethod
from collections.abc import Callable
from dataclasses import dataclass

from shared_core.logging.logger import get_logger
from shared_core.queue.constants import (
    DEFAULT_MAX_WORKERS,
    DEFAULT_MIN_WORKERS,
    DEFAULT_WORKER_HEALTH_CHECK_INTERVAL_SECONDS,
    DEFAULT_WORKER_RESTART_BACKOFF_SECONDS,
)
from shared_core.queue.exceptions import WorkerPoolError
from shared_core.queue.manager import QueueManager
from shared_core.queue.metrics import set_worker_count
from shared_core.types.queue import QueueMessage

logger = get_logger("shared_core.queue.worker")


class WorkerBase(ABC):
    """Base class every background queue worker implements.

    Subclasses implement :meth:`handle` with their business logic; this
    class owns queue declaration, consumption, and retry wiring.
    """

    queue_name: str

    def __init__(self, queue_manager: QueueManager) -> None:
        self._queue_manager = queue_manager

    @abstractmethod
    async def handle(self, message: QueueMessage) -> None:
        """Process a single message. Raise to trigger retry/dead-lettering."""

    async def start(self) -> None:
        """Declare the queue (with its dead-letter queue) and begin consuming."""
        await self._queue_manager.declare_queue_with_dlq(self.queue_name)
        logger.info("worker starting", extra={"extra_fields": {"queue": self.queue_name}})
        await self._queue_manager.consume(self.queue_name, self.handle)


@dataclass(frozen=True, slots=True)
class WorkerStatus:
    """One pool worker's health snapshot ("Worker Health")."""

    index: int
    running: bool
    restart_count: int
    last_heartbeat_seconds_ago: float


class WorkerPool:
    """Runs and supervises several concurrent :class:`WorkerBase` instances.

    Each pool worker is one independent consumer registration on its own
    :class:`~shared_core.queue.manager.QueueManager` (its own channel and
    prefetch window) -- running *N* gives *N* times the effective
    concurrency ("Concurrency Control"). Once registered, the underlying
    ``aio-pika`` robust connection already transparently reconnects and
    re-declares a dropped consumer on its own (see
    :func:`shared_core.queue.connection.create_connection`); this pool's
    "Worker Restart" supervises the *outer* failure a robust reconnect
    can't fix by itself -- the worker's own ``start()`` call raising
    (e.g. a bad queue declaration) -- by re-instantiating and
    re-registering that worker from scratch after a short backoff.
    """

    def __init__(
        self,
        worker_factory: Callable[[], WorkerBase],
        *,
        name: str,
        min_workers: int = DEFAULT_MIN_WORKERS,
        max_workers: int = DEFAULT_MAX_WORKERS,
        restart_backoff_seconds: float = DEFAULT_WORKER_RESTART_BACKOFF_SECONDS,
        health_check_interval_seconds: float = DEFAULT_WORKER_HEALTH_CHECK_INTERVAL_SECONDS,
    ) -> None:
        if min_workers < 1 or max_workers < min_workers:
            raise WorkerPoolError(
                f"Invalid worker bounds for pool '{name}': "
                f"min_workers={min_workers}, max_workers={max_workers}."
            )
        self._worker_factory = worker_factory
        self.name = name
        self._min_workers = min_workers
        self._max_workers = max_workers
        self._restart_backoff_seconds = restart_backoff_seconds
        self._health_check_interval_seconds = health_check_interval_seconds
        self._tasks: dict[int, asyncio.Task[None]] = {}
        self._restart_counts: dict[int, int] = {}
        self._heartbeats: dict[int, float] = {}
        self._running = False

    @property
    def worker_count(self) -> int:
        """The number of currently-running worker tasks ("Worker Count")."""
        return len(self._tasks)

    async def start(self) -> None:
        """Start ``min_workers`` workers ("Dynamic Workers": begins at the pool's floor)."""
        self._running = True
        for index in range(self._min_workers):
            self._spawn(index)
        set_worker_count(self.name, self.worker_count)

    def _spawn(self, index: int) -> None:
        self._heartbeats[index] = time.monotonic()
        self._tasks[index] = asyncio.create_task(self._run_worker(index))

    async def _run_worker(self, index: int) -> None:
        while self._running:
            try:
                worker = self._worker_factory()
                await worker.start()
                self._heartbeats[index] = time.monotonic()
                while self._running:
                    self._heartbeats[index] = time.monotonic()
                    await asyncio.sleep(self._health_check_interval_seconds)
            except asyncio.CancelledError:
                raise
            except Exception:
                self._restart_counts[index] = self._restart_counts.get(index, 0) + 1
                logger.warning(
                    "worker crashed, restarting",
                    extra={
                        "extra_fields": {
                            "pool": self.name,
                            "worker_index": index,
                            "restart_count": self._restart_counts[index],
                        }
                    },
                )
                await asyncio.sleep(self._restart_backoff_seconds)

    async def scale_to(self, count: int) -> None:
        """Scale the pool to exactly *count* workers ("Dynamic Workers").

        Raises:
            WorkerPoolError: If *count* is outside ``[min_workers, max_workers]``.
        """
        if not self._min_workers <= count <= self._max_workers:
            raise WorkerPoolError(
                f"Cannot scale pool '{self.name}' to {count} workers: "
                f"must be between {self._min_workers} and {self._max_workers}."
            )
        current = set(self._tasks)
        desired = set(range(count))
        for index in desired - current:
            self._spawn(index)
        for index in current - desired:
            task = self._tasks.pop(index)
            task.cancel()
            self._heartbeats.pop(index, None)
        set_worker_count(self.name, self.worker_count)

    def status(self) -> list[WorkerStatus]:
        """Return a health snapshot of every currently-running worker ("Worker Health")."""
        now = time.monotonic()
        return [
            WorkerStatus(
                index=index,
                running=not task.done(),
                restart_count=self._restart_counts.get(index, 0),
                last_heartbeat_seconds_ago=now - self._heartbeats.get(index, now),
            )
            for index, task in sorted(self._tasks.items())
        ]

    async def shutdown(self, *, timeout_seconds: float = 10.0) -> None:
        """Stop every worker ("Worker Shutdown")."""
        self._running = False
        tasks = list(self._tasks.values())
        for task in tasks:
            task.cancel()
        if tasks:
            await asyncio.wait(tasks, timeout=timeout_seconds)
        self._tasks.clear()
        self._heartbeats.clear()
        set_worker_count(self.name, 0)


__all__ = ["WorkerBase", "WorkerPool", "WorkerStatus"]
