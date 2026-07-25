"""Persistent queue integration.

Per docs/026_Enterprise_Scheduler_Framework.md.txt "PERFORMANCE":
Persistent Queue Integration; "SCHEDULER PRINCIPLES": "Scheduler shall
survive restarts", "Scheduler shall never lose scheduled jobs". Reuses
:class:`shared_core.queue.producer.Producer`/
:class:`shared_core.queue.consumer.Consumer` directly (already
RabbitMQ-backed with durable queues, dead-lettering, and retry/backoff)
rather than building a second message broker integration -- this module
only defines the small envelope a due job is published as, and how a
worker turns it back into a job id.

Only a job's id crosses the queue, never its ``fn``: a job's executable
is process-local (registered in :mod:`shared_core.scheduler.registry`),
so a worker on any node resolves ``fn`` itself after receiving the id,
rather than the queue attempting to (de)serialize a callable.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from datetime import UTC, datetime

from shared_core.queue.consumer import Consumer
from shared_core.queue.manager import QueueManager
from shared_core.queue.producer import Producer
from shared_core.types.queue import QueueMessage

DEFAULT_JOB_QUEUE_NAME = "scheduler.due-jobs"

JobIdHandler = Callable[[str], Awaitable[None]]


def build_due_job_message(job_id: str) -> QueueMessage:
    """Build the envelope published when *job_id* becomes due."""
    return {"job_id": job_id, "enqueued_at": datetime.now(UTC).isoformat()}


def job_id_from_message(message: QueueMessage) -> str:
    """Extract the job id from a due-job queue message.

    Raises:
        KeyError: If *message* isn't a due-job envelope.
    """
    return str(message["job_id"])


class JobQueue:
    """Publishes due jobs to, and consumes them from, a durable RabbitMQ queue."""

    def __init__(
        self,
        queue_manager: QueueManager,
        *,
        queue_name: str = DEFAULT_JOB_QUEUE_NAME,
    ) -> None:
        self._queue_manager = queue_manager
        self._queue_name = queue_name
        self._producer = Producer(queue_manager)
        self._consumer = Consumer(queue_manager)

    async def declare(self) -> None:
        """Declare the queue (and its dead-letter queue) before first use."""
        await self._queue_manager.declare_queue_with_dlq(self._queue_name)

    async def enqueue(self, job_id: str) -> None:
        """Publish *job_id* as due for immediate execution."""
        await self._producer.publish(self._queue_name, build_due_job_message(job_id))

    async def enqueue_at(self, job_id: str, *, at: datetime) -> None:
        """Publish *job_id* to become due at a specific future time ("Delayed Jobs")."""
        await self._producer.publish_scheduled(
            self._queue_name, build_due_job_message(job_id), at=at
        )

    async def consume(self, handler: JobIdHandler) -> None:
        """Subscribe *handler* to receive due job ids as they arrive."""

        async def _dispatch(message: QueueMessage) -> None:
            await handler(job_id_from_message(message))

        await self._consumer.subscribe(self._queue_name, _dispatch)


__all__ = [
    "DEFAULT_JOB_QUEUE_NAME",
    "JobIdHandler",
    "JobQueue",
    "build_due_job_message",
    "job_id_from_message",
]
